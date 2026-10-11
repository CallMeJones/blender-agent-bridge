"""Fixed-template background remeshing/baking entry point, not arbitrary Python."""
from __future__ import annotations

import json
import os
import traceback
import bpy
from . import job_runtime, retopology, retopology_baking


def run(config):
    def progress(phase, amount, message=""):
        if os.path.isfile(config["cancel_path"]):
            raise RuntimeError("Retopology job cancelled")
        job_runtime.write_json(config["status_path"], {"status": "running", "phase": phase,
                                                     "progress": amount, "message": message})
    with bpy.data.libraries.load(config["input_path"], link=False) as (available, loaded):
        loaded.objects = list(config["snapshot_names"])
    for obj in loaded.objects:
        if obj is None:
            raise ValueError("Snapshot source is missing")
        bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    options = config["options"]
    results, output_objects = [], []
    for index, source_name in enumerate(config["source_snapshots"]):
        source = bpy.data.objects[source_name]
        progress("cleanup", index / len(config["source_snapshots"]), source_name)
        if config["kind"] == "bake":
            target = bpy.data.objects[config["target_snapshot"]]
        else:
            target = retopology.static_copy(bpy.context, source, config["source_names"][index] + "_retopo", independent_materials=False)
            retopology.clean_mesh(target.data, merge_distance_ratio=options["merge_distance_ratio"])
            retopology_baking._activate(target)
            previous_faces = len(target.data.polygons)
            progress("remesh", index / len(config["source_snapshots"]), options["method"])
            if options["method"] == "quadriflow":
                # Runtime feature checks keep the same fixed operator template compatible with 4.2–5.1.
                kwargs = {"mode": "FACES", "target_faces": options["target_faces"],
                          "use_mesh_symmetry": options["use_symmetry"], "use_preserve_sharp": options["preserve_sharp"],
                          "use_preserve_boundary": options["preserve_boundary"], "seed": options["seed"]}
                props = bpy.ops.object.quadriflow_remesh.get_rna_type().properties.keys()
                kwargs = {key: value for key, value in kwargs.items() if key in props}
                if "FINISHED" not in bpy.ops.object.quadriflow_remesh(**kwargs):
                    raise RuntimeError("QuadriFlow could not remesh this source; inspect manifoldness and surface islands")
                if options["target_faces"] < previous_faces * .5 and len(target.data.polygons) >= previous_faces:
                    raise RuntimeError("QuadriFlow returned the original topology instead of a reduced result")
            else:
                # Collapse decimation operates on triangles; measure that count rather than polygon count.
                triangles = sum(len(f.vertices) - 2 for f in target.data.polygons)
                if triangles > options["target_faces"]:
                    modifier = target.modifiers.new("Retopology Decimate", "DECIMATE")
                    modifier.ratio = options["target_faces"] / triangles
                    modifier.use_collapse_triangulate = True
                    if "FINISHED" not in bpy.ops.object.modifier_apply(modifier=modifier.name):
                        raise RuntimeError("Decimation failed")
            retopology.validate_mesh(target.data)
            if options["project_to_source"]:
                _, _, bvh = retopology._world_surface(source, bpy.context.evaluated_depsgraph_get())
                inverse = target.matrix_world.inverted_safe()
                for vertex in target.data.vertices:
                    nearest = bvh.find_nearest(target.matrix_world @ vertex.co)
                    if nearest and nearest[0] is not None:
                        vertex.co = inverse @ nearest[0]
                target.data.update()
        target.name = config["source_names"][index] + "_retopo_result"
        target["agent_bridge_retopology_source"] = config["source_names"][index]
        target["agent_bridge_retopology_job"] = config["job_id"]
        target["agent_bridge_retopology_intended_use"] = options["intended_use"]
        if config["kind"] == "remesh":
            for face in target.data.polygons:
                face.use_smooth = True
        baked = None
        if options["bake_textures"]:
            baked = retopology_baking.bake_atlas(source, target, os.path.join(config["job_dir"], "textures", str(index)),
                                               resolution=options["resolution"], map_types=options["map_types"],
                                               samples=options["samples"], margin=options["margin"],
                                               ray_distance_ratio=options["ray_distance_ratio"],
                                               cage_extrusion_ratio=options["cage_extrusion_ratio"], uv_mode=options["uv_mode"],
                                               progress=progress)
        comparison = retopology.evaluate_result(bpy.context, source_object_name=source.name, target_object_name=target.name,
                                                intended_use=options["intended_use"], max_deviation_ratio=options["max_deviation_ratio"])
        results.append({"source": config["source_names"][index], "object": target.name,
                        "comparison": comparison["comparison"], "topology": comparison["target"],
                        "findings": comparison["findings"], "bake": baked, "animation_ready": False})
        output_objects.append(target)
    progress("save", .99)
    bpy.data.libraries.write(config["result_path"], set(output_objects), path_remap="ABSOLUTE", fake_user=False, compress=True)
    job_runtime.write_json(config["result_report_path"], {"ok": True, "results": results,
                                                         "object_names": [o.name for o in output_objects]})
    job_runtime.write_json(config["status_path"], {"status": "completed", "progress": 1.0, "message": "Retopology result ready for preview import"})


def main(config_path):
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    try:
        run(config)
        return 0
    except Exception as error:
        job_runtime.write_json(config["status_path"], {"status": "failed", "progress": 0,
                                                     "message": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()})
        return 1
