"""Structured pump study: deliberate mechanical parts, editable quad strips.
This is an authored rebuild fitted to the Tripo reference, not an automatic
retopology solver and not a claim of exact surface equivalence.
"""
import bpy
import bmesh
import math
from mathutils import Vector
COLLECTION='Pump human - editable parts'
CENTER_X=-.029
CENTER_Z=-.045
PARTS=[]
MATERIALS={}
COL=None

def material(name,color,metallic=0,roughness=.4):
    mat=bpy.data.materials.new('Human Pump '+name)
    mat.use_nodes=True
    shader=mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(*color,1)
    shader.inputs['Metallic'].default_value=metallic
    shader.inputs['Roughness'].default_value=roughness
    if name in {'rubber','interior'}:
        shader.inputs['Specular IOR Level'].default_value=.15
    MATERIALS[name]=mat
    return mat

def mesh_part(name,verts,faces,mat,smooth=True):
    mesh=bpy.data.meshes.new('HP '+name+' mesh')
    mesh.from_pydata(verts,[],faces)
    assert not mesh.validate(), name+' invalid mesh'
    mesh.update()
    bm=bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    obj=bpy.data.objects.new('HP '+name,mesh)
    COL.objects.link(obj)
    obj.data.materials.append(MATERIALS[mat])
    for face in mesh.polygons:
        face.use_smooth=smooth and len(face.vertices)==4
    obj['human_topology_part']=name
    obj['topology_approach']='authored mechanical forms and regular loops'
    PARTS.append(obj)
    return obj

def box(name,center,size,mat,bevel=.004):
    x,y,z=[s/2 for s in size]
    c=Vector(center)
    verts=[c+Vector(v) for v in [(-x,-y,-z),(-x,-y,z),(-x,y,-z),(-x,y,z),
                                (x,-y,-z),(x,-y,z),(x,y,-z),(x,y,z)]]
    obj=mesh_part(name,verts,[(0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),
                              (0,2,3,1),(4,5,7,6)],mat,smooth=False)
    if bevel:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active=obj
        mod=obj.modifiers.new('Purposeful edge bevel','BEVEL')
        mod.width=bevel
        mod.segments=1
        mod.affect='EDGES'
        bpy.ops.object.modifier_apply(modifier=mod.name)
        for p in obj.data.polygons:p.use_smooth=False
    return obj

def axial(name,profile,mat,center=(CENTER_X,CENTER_Z),segments=32,axis='Y',cap=True,phase=0):
    verts=[]
    for coordinate,radius in profile:
        for i in range(segments):
            a=2*math.pi*i/segments+phase
            u=radius*math.cos(a)+center[0]
            v=radius*math.sin(a)+center[1]
            verts.append((u,coordinate,v) if axis=='Y' else (u,v,coordinate))
    faces=[]
    for j in range(len(profile)-1):
        for i in range(segments):
            a=j*segments+i
            b=j*segments+(i+1)%segments
            faces.append((a,b,b+segments,a+segments))
    if cap:
        faces.extend([tuple(range(segments-1,-1,-1)),tuple((len(profile)-1)*segments+i for i in range(segments))])
    return mesh_part(name,verts,faces,mat)

def ring(name,axial_center,radius,thickness,depth,mat,segments=32,axis='Y',center=(CENTER_X,CENTER_Z)):
    a=axial_center-depth/2
    b=axial_center+depth/2
    profiles=[(a,radius),(b,radius),(b,radius-thickness),(a,radius-thickness)]
    verts=[]
    for coordinate,r in profiles:
        for i in range(segments):
            t=2*math.pi*i/segments
            u=center[0]+r*math.cos(t)
            v=center[1]+r*math.sin(t)
            verts.append((u,coordinate,v) if axis=='Y' else (u,v,coordinate))
    faces=[(j*segments+i,j*segments+(i+1)%segments,
            ((j+1)%4)*segments+(i+1)%segments,((j+1)%4)*segments+i)
           for j in range(4) for i in range(segments)]
    return mesh_part(name,verts,faces,mat)

def catmull(points,per_segment):
    p=[Vector(v) for v in points]
    samples=[]
    for j in range(len(p)-1):
        a=p[max(0,j-1)];b=p[j];c=p[j+1];d=p[min(len(p)-1,j+2)]
        for k in range(per_segment):
            t=k/per_segment
            samples.append(.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t))
    samples.append(p[-1])
    return samples

def sweep(name,path,section,mat,reference=(1,0,0),radii=None):
    path=[Vector(p) for p in path]
    reference=Vector(reference)
    verts=[]
    for j,p in enumerate(path):
        tangent=(path[min(j+1,len(path)-1)]-path[max(j-1,0)]).normalized()
        normal=reference-tangent*reference.dot(tangent)
        if normal.length<1e-6:
            normal=tangent.cross(Vector((0,0,1)))
        normal.normalize()
        binormal=tangent.cross(normal).normalized()
        scale=radii[j] if radii else 1
        verts.extend(p+scale*(normal*u+binormal*v) for u,v in section)
    n=len(section)
    faces=[(j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i)
           for j in range(len(path)-1) for i in range(n)]
    faces.extend([tuple(range(n-1,-1,-1)),tuple((len(path)-1)*n+i for i in range(n))])
    return mesh_part(name,verts,faces,mat)

def rounded_section(width,height,bevel):
    x=width/2;y=height/2;b=bevel
    return [(-x+b,-y),(x-b,-y),(x,-y+b),(x,y-b),(x-b,y),(-x+b,y),(-x,y-b),(-x,-y+b)]

def circle_section(radius,n):
    return [(radius*math.cos(2*math.pi*i/n),radius*math.sin(2*math.pi*i/n)) for i in range(n)]

def bolt(name,position,axis='Z',radius=.012):
    x,y,z=position
    center=(x,y) if axis=='Z' else (x,z)
    coordinate=z if axis=='Z' else y
    axial(name,[(coordinate,radius*.95),(coordinate+.009,radius),
                (coordinate+.011,radius*.82)],'silver',center=center,segments=6,axis=axis,phase=math.pi/6)

def torus(name,center,major,minor,mat,n=24,m=6):
    cx,cy,cz=center
    verts=[]
    for i in range(n):
        a=2*math.pi*i/n
        for j in range(m):
            b=2*math.pi*j/m
            verts.append((cx+(major+minor*math.cos(b))*math.cos(a),
                          cy+(major+minor*math.cos(b))*math.sin(a),cz+minor*math.sin(b)))
    faces=[(i*m+j,((i+1)%n)*m+j,((i+1)%n)*m+(j+1)%m,i*m+(j+1)%m)
           for i in range(n) for j in range(m)]
    return mesh_part(name,verts,faces,mat)

def combine():
    verts=[];faces=[];indices=[];smooth=[]
    mats=list(MATERIALS.values())
    for obj in PARTS:
        offset=len(verts)
        verts.extend(obj.matrix_world@v.co for v in obj.data.vertices)
        for p in obj.data.polygons:
            faces.append(tuple(offset+i for i in p.vertices))
            indices.append(mats.index(obj.data.materials[p.material_index]))
            smooth.append(p.use_smooth)
    mesh=bpy.data.meshes.new('Human pump assembled quad strips')
    mesh.from_pydata(verts,[],faces)
    assert not mesh.validate()
    mesh.update()
    obj=bpy.data.objects.new('Pump Human Topology Preview',mesh)
    bpy.context.scene.collection.objects.link(obj)
    for mat in mats:mesh.materials.append(mat)
    for p,idx,shade in zip(mesh.polygons,indices,smooth):
        p.material_index=idx;p.use_smooth=shade
    obj['human_topology_part']='assembled review copy; editable named parts are retained'
    obj['human_topology_candidate']=True
    return obj

def build():
    global COL
    if bpy.data.collections.get(COLLECTION) is not None:
        raise ValueError('Candidate already exists; preserve it or rename before rebuilding')
    if bpy.context.mode != 'OBJECT':
        raise ValueError('Leave Edit/Sculpt mode before building the example')
    PARTS.clear()
    MATERIALS.clear()
    COL=bpy.data.collections.new(COLLECTION)
    bpy.context.scene.collection.children.link(COL)
    material('yellow',(.68,.44,.12),.45,.32)
    material('silver',(.48,.50,.49),.75,.3)
    material('rubber',(.009,.010,.009),0,.82)
    material('fan cover',(.09,.095,.09),.25,.5)
    material('brass',(.58,.39,.13),.8,.28)
    material('interior',(.003,.004,.004),0,.9)

    # A hollow frame uses four flat beams, not triangles distributed over a box.
    for x,label in [(-.245,'left'),(.187,'right')]:
        box('base '+label+' rail',(x,.02,-.298),(.048,.804,.059),'yellow',.005)
    for y,label in [(-.360,'front'),(.397,'rear')]:
        box('base '+label+' crossmember',(CENTER_X,y,-.298),(.434,.044,.059),'yellow',.004)
    for x,label in [(-.223,'L'),(.165,'R')]:
        for y,tag in [(-.310,'front'),(.357,'rear')]:
            axial('rubber foot '+tag+label,[(-.394,.05),(-.389,.051),(-.337,.044),(-.333,.041)],
                  'rubber',center=(x,y),segments=16,axis='Z')
            bolt('frame bolt '+tag+label,(x,y,-.264),radius=.011)

    axial('motor core',[(-.045,.190),(-.035,.198),(.303,.198),(.322,.191)],'yellow',segments=32)
    axial('rear fan cover',[(.313,.204),(.333,.214),(.467,.214),(.488,.209),(.498,.199)],
          'fan cover',segments=32)
    ring('motor front flange',-.074,.223,.030,.045,'yellow',segments=32)
    ring('motor rear flange',.304,.210,.022,.023,'yellow',segments=32)
    # Each fin is one purposeful strip. Small grooves are shading detail.
    for i in range(24):
        a=2*math.pi*i/24
        ca,sa=math.cos(a),math.sin(a)
        points=[]
        for y,r,t in [(-.038,.192,-.004),(-.038,.230,-.004),(-.038,.230,.004),(-.038,.192,.004),
                      (.291,.192,-.004),(.291,.230,-.004),(.291,.230,.004),(.291,.192,.004)]:
            points.append((CENTER_X+r*ca-t*sa,y,CENTER_Z+r*sa+t*ca))
        mesh_part('cooling fin %02d'%i,points,[(0,1,2,3),(4,7,6,5),(0,4,5,1),
                   (1,5,6,2),(2,6,7,3),(3,7,4,0)],'yellow',smooth=False)
    box('terminal box',(CENTER_X,.130,.197),(.246,.283,.105),'yellow',.006)
    box('terminal lid',(CENTER_X,.130,.253),(.272,.306,.019),'yellow',.004)
    for x in [-.136,.078]:
        for y in [.009,.251]:
            bolt('terminal lid bolt',(x,y,.265),radius=.010)
    for x in [-.147,.089]:
        for y in [-.035,.279]:
            box('motor mounting bracket',(x,y,-.25),(.035,.045,.052),'yellow',.002)
            bolt('motor mount bolt',(x,y,-.264),radius=.010)

    axial('pump volute shell',[(-.443,.172),(-.427,.183),(-.396,.190),(-.330,.189),
                              (-.283,.184),(-.256,.167)],'silver',segments=40)
    axial('pump rear coupling',[(-.264,.161),(-.245,.166),(-.158,.174),(-.139,.202)],
          'silver',segments=32)
    ring('pump rear flange',-.135,.209,.027,.024,'silver',segments=40)
    ring('front guard rim',-.457,.189,.014,.022,'silver',segments=40)
    axial('dark interior',[(-.444,.155),(-.435,.155)],'interior',segments=24)
    for sign in [-1,1]:
        # Tapered mounting struts stop at the base and follow the casing rim.
        x=CENTER_X+sign*.177
        box('pump support %s'%sign,(x,-.257,-.103),(.032,.037,.307),'silver',.003)
    for i in range(6):
        a=2*math.pi*i/6
        x=CENTER_X+.197*math.cos(a)
        z=CENTER_Z+.197*math.sin(a)
        bolt('front flange bolt %d'%i,(x,-.468,z),axis='Y',radius=.014)
        bolt('rear flange bolt %d'%i,(x,-.150,z),axis='Y',radius=.012)
    # Curved guard bars have only enough longitudinal loops to follow the dome.
    guard_r=.174
    for i,offset in enumerate([-.116,-.058,0,.058,.116]):
        extent=math.sqrt(guard_r**2-offset**2)
        path=[]
        for j in range(7):
            z=-extent+2*extent*j/6
            y=-.465-.030*(1-(z/guard_r)**2)*(1-(offset/guard_r)**2)
            path.append((CENTER_X+offset,y,CENTER_Z+z))
        sweep('guard vertical bar %d'%i,path,rounded_section(.012,.010,.002),'silver',reference=(1,0,0))
        path=[]
        for j in range(7):
            x=-extent+2*extent*j/6
            y=-.464-.027*(1-(x/guard_r)**2)*(1-(offset/guard_r)**2)
            path.append((CENTER_X+x,y,CENTER_Z+offset))
        sweep('guard horizontal bar %d'%i,path,rounded_section(.010,.012,.002),'silver',reference=(0,0,1))

    # An eight-sided rounded rectangular section gives the handle real flat faces.
    handle=catmull([(CENTER_X,-.104,.173),(CENTER_X,-.071,.300),(CENTER_X,-.025,.348),
                   (CENTER_X,.045,.363),(CENTER_X,.253,.363),(CENTER_X,.307,.347),
                   (CENTER_X,.340,.292),(CENTER_X,.357,.178)],3)
    sweep('carry handle',handle,rounded_section(.072,.053,.009),'yellow',reference=(1,0,0))
    grip=[(CENTER_X,y,.364) for y in [.043,.048,.090,.132,.174,.216,.250,.254]]
    sweep('rubber handle grip',grip,rounded_section(.078,.061,.009),'rubber',reference=(1,0,0))
    for y in [-.097,.355]:
        box('handle attachment',(CENTER_X,y,.179),(.098,.049,.027),'yellow',.003)
        for x in [-.063,.007]:bolt('handle mount bolt',(x,y,.195),radius=.010)

    hose=catmull([(.115,-.310,.178),(.238,-.285,.153),(.319,-.215,.094),
                  (.326,-.156,.012),(.282,-.156,-.073),(.194,-.175,-.118)],8)
    radii=[1+.045*math.cos(2*math.pi*j/2) for j in range(len(hose))]
    sweep('return hose',hose,circle_section(.033,10),'rubber',reference=(0,1,0),radii=radii)
    for tag,point,tangent in [('upper',hose[0],hose[1]-hose[0]),('lower',hose[-1],hose[-1]-hose[-2])]:
        tangent.normalize()
        sleeve=[point+tangent*(v if tag=='upper' else -v) for v in [-.015,0,.021]]
        sweep('hose '+tag+' collar',sleeve,circle_section(.037,12),'silver',reference=(0,1,0))
    sweep('upper valve hose nozzle',[(.063,-.303,.169),(.085,-.306,.175),(.132,-.312,.178)],
          circle_section(.026,12),'brass',reference=(0,1,0))
    sweep('lower casing hose coupling',[(.130,-.175,-.118),(.164,-.175,-.118),(.207,-.175,-.118)],
          circle_section(.028,12),'silver',reference=(0,1,0))

    axial('top inlet neck',[(.137,.037),(.210,.035),(.220,.042)],'silver',
          center=(-.088,-.346),segments=16,axis='Z')
    axial('inlet cap',[(.220,.038),(.231,.041),(.310,.038),(.329,.035)],'silver',
          center=(-.088,-.346),segments=16,axis='Z')
    axial('valve body',[(.116,.025),(.238,.026),(.251,.022)],'brass',
          center=(.049,-.303),segments=12,axis='Z')
    axial('valve spindle',[(.245,.009),(.284,.009)],'silver',
          center=(.049,-.303),segments=10,axis='Z')
    torus('valve handwheel',(.049,-.303,.291),.044,.006,'brass',n=24,m=6)
    axial('handwheel hub',[(.282,.012),(.299,.012)],'brass',
          center=(.049,-.303),segments=12,axis='Z')
    for i in range(5):
        a=2*math.pi*i/5
        spoke=[(.049+r*math.cos(a),-.303+r*math.sin(a),.291) for r in [.010,.024,.044]]
        sweep('valve spoke %d'%i,spoke,circle_section(.0038,6),'brass',reference=(0,0,1))
    # Side outlet is a short low-sided tube with explicit coupling loops.
    outlet=[(-.188,-.200,-.080),(-.235,-.200,-.080),(-.320,-.200,-.080),(-.359,-.200,-.080)]
    sweep('side outlet',outlet,circle_section(.024,12),'silver',reference=(0,0,1))
    for x in [-.245,-.328]:
        sweep('outlet coupling',[(x-.008,-.200,-.080),(x+.008,-.200,-.080)],
              circle_section(.028,12),'silver',reference=(0,0,1))
    return combine(),PARTS

if __name__=='__main__':
    preview,parts=build()
    print('HUMAN_PUMP_BUILD: '+str(dict(parts=len(parts),faces=len(preview.data.polygons),
          triangles=sum(len(p.vertices)-2 for p in preview.data.polygons))))
