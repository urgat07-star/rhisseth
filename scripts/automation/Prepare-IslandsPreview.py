"""Move small ocean islands by the shortest integer translation; never redraw land."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'app/frontend/terrain-map-group3-artistic-v5-no-grid.png'
DEST = ROOT / 'reports/previews/islands-v2'
parser = argparse.ArgumentParser()
parser.add_argument('--analyze', action='store_true')
args = parser.parse_args()
image = np.asarray(Image.open(SOURCE).convert('RGB')).copy()
height, width = image.shape[:2]
assert (width, height) == (1508, 1043)
# Include sand and the bright shoreline, excluding the cyan ocean.
rgb = image.astype(np.float32)
land = ((rgb[:,:,0] > .85*rgb[:,:,2]) & (rgb[:,:,1] > .90*rgb[:,:,2])).astype(np.uint8)
land = cv2.morphologyEx(land, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8))
count, labels, stats, centroids = cv2.connectedComponentsWithStats(land, 8)
HALF_WIDTH = math.sqrt(3)*80/2 * width/3200
VERT_RADIUS = 80*height/2200
STEP_X = 2*HALF_WIDTH
STEP_Y = 120*height/2200
SLOPE = VERT_RADIUS/(2*HALF_WIDTH)
NORMALS = np.array([[1,0],[-1,0],[SLOPE,1],[-SLOPE,1],[SLOPE,-1],[-SLOPE,-1]])
LIMITS = np.array([HALF_WIDTH, HALF_WIDTH, VERT_RADIUS, VERT_RADIUS, VERT_RADIUS, VERT_RADIUS])
NORM_LENGTHS = np.linalg.norm(NORMALS,axis=1)
CLEARANCE = 1.5
KERNEL3 = np.ones((3,3),np.uint8)
KERNEL5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))

def cell_at(x,y):
    rf=y/STEP_Y
    qf=x/STEP_X-rf/2
    sf=-qf-rf
    q,r,s=round(qf),round(rf),round(sf)
    dq,dr,ds=abs(q-qf),abs(r-rf),abs(s-sf)
    if dq>dr and dq>ds:
        q=-r-s
    elif dr>ds:
        r=-q-s
    return q,r

def cell_center(q,r):
    return np.array([STEP_X*(q+r/2),STEP_Y*r])

components=[]
all_core=np.zeros((height,width),np.uint8)
for label in range(1,count):
    x,y,w,h,area=map(int,stats[label])
    if area < 12:
        continue
    comp=(labels[y:y+h,x:x+w]==label).astype(np.uint8)
    contours,_=cv2.findContours(comp,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(comp,contours,-1,1,cv2.FILLED)
    # Two extra pixels retain shoreline antialiasing and keep grid clear of the beach.
    patch=np.pad(comp,8)
    core=cv2.dilate(patch,KERNEL5,iterations=1)
    py,px=np.nonzero(core)
    points=np.column_stack((px+x-8,py+y-8))
    valid=(points[:,0]>=0)&(points[:,0]<width)&(points[:,1]>=0)&(points[:,1]<height)
    points=points[valid]
    all_core[points[:,1],points[:,0]]=1
    components.append({'id':label,'area':area,'bounds':[x,y,w,h],'points':points,
                       'centroid':np.array(centroids[label]),'support':(points @ NORMALS.T).max(axis=0)})

# Restrict to isolated ocean islands: land enclosed within continents/lakes is excluded.
# Closing the major land silhouettes stops narrow rivers admitting ocean into interiors.
major=np.zeros((height,width),np.uint8)
for c in components:
    if c['area']>6000:
        major[c['points'][:,1],c['points'][:,0]]=1
major=cv2.morphologyEx(major,cv2.MORPH_CLOSE,np.ones((11,11),np.uint8))
# Flood-fill only broad water accessible from an edge.
water=(1-major).astype(np.uint8)
water=cv2.erode(water,np.ones((7,7),np.uint8),iterations=1)
nwater,water_labels,wstats,_=cv2.connectedComponentsWithStats(water,8)
edge_labels=set(np.unique(np.concatenate((water_labels[0],water_labels[-1],
                                         water_labels[:,0],water_labels[:,-1]))))
edge_labels.discard(0)
ocean=np.isin(water_labels,list(edge_labels)).astype(np.uint8)
ocean=cv2.dilate(ocean,np.ones((9,9),np.uint8))
# Avoid mistaking small fragments along a mainland shoreline for detached islands.
major_guard=cv2.dilate(major,np.ones((5,5),np.uint8))
occupancy=all_core.copy()
report=[]
plans=[]
offsets=np.array(sorted(((dx,dy) for dx in range(-80,81) for dy in range(-80,81)),
                        key=lambda p:(p[0]*p[0]+p[1]*p[1],abs(p[0])+abs(p[1]),p[1],p[0])),dtype=int)
for c in sorted(components,key=lambda item:-item['area']):
    pts=c['points']
    entry={'id':c['id'],'area_pixels':c['area'],'original_bounds':c['bounds'],
           'original_center':[round(float(v),3) for v in c['centroid']],
           'original_hex':list(cell_at(*c['centroid']))}
    x,y,w,h=c['bounds']
    if w+4>2*HALF_WIDTH-2*CLEARANCE or h+4>2*VERT_RADIUS-2*CLEARANCE:
        entry['status']='larger_than_hex'
        report.append(entry)
        continue
    if not ocean[int(c['centroid'][1]),int(c['centroid'][0])] or np.any(major_guard[pts[:,1],pts[:,0]]):
        entry['status']='not_isolated_ocean_island'
        report.append(entry)
        continue
    q,r=cell_at(*c['centroid'])
    options=[]
    for rr in range(r-2,r+3):
        for qq in range(q-2,q+3):
            center=cell_center(qq,rr)
            residual=LIMITS-CLEARANCE*NORM_LENGTHS+center @ NORMALS.T-c['support']
            valid=np.all(offsets @ NORMALS.T <= residual+1e-7,axis=1)
            for candidate in offsets[valid]:
                dx,dy=map(int,candidate)
                dest=pts+candidate
                if (dest[:,0]<0).any() or (dest[:,0]>=width).any() or (dest[:,1]<0).any() or (dest[:,1]>=height).any():
                    continue
                # Check against all other islands/coasts, including earlier moved islands.
                own=occupancy[pts[:,1],pts[:,0]].copy()
                occupancy[pts[:,1],pts[:,0]]=0
                collision=np.any(occupancy[dest[:,1],dest[:,0]])
                occupancy[pts[:,1],pts[:,0]]=own
                if collision:
                    continue
                dist2=dx*dx+dy*dy
                center_distance=np.sum((c['centroid']+candidate-center)**2)
                options.append((dist2,center_distance,dx,dy,qq,rr))
                break
    if not options:
        entry['status']='shape_does_not_fit_one_hex'
        report.append(entry)
        continue
    _,_,dx,dy,q,r=min(options)
    target=pts+np.array([dx,dy])
    margin=(LIMITS+cell_center(q,r) @ NORMALS.T-(target @ NORMALS.T).max(axis=0))/NORM_LENGTHS
    entry.update({'target_hex':[q,r],'translation_px':[dx,dy],
                  'distance_px':round(math.hypot(dx,dy),3),'clearance_px':round(float(margin.min()),3)})
    entry['status']='unchanged_inside_hex' if dx==0 and dy==0 else 'moved'
    report.append(entry)
    if dx or dy:
        occupancy[pts[:,1],pts[:,0]]=0
        occupancy[target[:,1],target[:,0]]=1
        plans.append((c,dx,dy))
DEST.mkdir(parents=True,exist_ok=True)
summary={'source':str(SOURCE.relative_to(ROOT)),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
         'canvas':[width,height],'radius_svg':80,'clearance_px':CLEARANCE,
         'strategy':'minimum integer translation; preserve source island RGB; restore ocean locally',
         'moved_count':len(plans),'islands':report}
(DEST/'placement-analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
for entry in report:
    if entry['status'] not in ('larger_than_hex','not_isolated_ocean_island'):
        print(json.dumps(entry))
if args.analyze:
    print('Analysis only; moved islands:',len(plans))
    raise SystemExit(0)

# Restore only the small ocean patches vacated by moved islands.
remove=np.zeros((height,width),np.uint8)
moved_ids={c['id'] for c,_,_ in plans}
protected=np.zeros((height,width),np.uint8)
for c in components:
    target_mask=remove if c['id'] in moved_ids else protected
    target_mask[c['points'][:,1],c['points'][:,0]]=1
remove=cv2.dilate(remove,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(29,29)),iterations=1)
remove[protected!=0]=0
output=cv2.inpaint(image,remove*255,5,cv2.INPAINT_TELEA)
edited=remove.copy()
for c,dx,dy in plans:
    pts=c['points']
    # Core includes ALL original land; only the surrounding WATER is feathered.
    core=np.zeros((height,width),np.uint8)
    core[pts[:,1],pts[:,0]]=1
    outer=cv2.dilate(core,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(17,17)),iterations=1)
    outside_distance=cv2.distanceTransform(1-core,cv2.DIST_L2,5)
    alpha=np.clip(1-outside_distance/9,0,1)*outer
    alpha[(all_core!=0)&(core==0)]=0
    sy,sx=np.nonzero(alpha>0)
    tx,ty=sx+dx,sy+dy
    valid=(tx>=0)&(tx<width)&(ty>=0)&(ty<height)
    sx,sy,tx,ty=sx[valid],sy[valid],tx[valid],ty[valid]
    # Do not disturb the existing shoreline of a stationary island.
    current_target=np.zeros((height,width),np.uint8)
    target=pts+np.array([dx,dy])
    current_target[target[:,1],target[:,0]]=1
    usable=(protected[ty,tx]==0)&((occupancy[ty,tx]==0)|(current_target[ty,tx]!=0))
    sx,sy,tx,ty=sx[usable],sy[usable],tx[usable],ty[usable]
    a=alpha[sy,sx,None]
    output[ty,tx]=np.round(image[sy,sx]*a+output[ty,tx]*(1-a)).astype(np.uint8)
    edited[ty,tx]=1
    target=pts+np.array([dx,dy])
    assert np.array_equal(output[target[:,1],target[:,0]],image[pts[:,1],pts[:,0]]),'Moved island RGB changed'
assert np.array_equal(output[protected!=0],image[protected!=0]),'Stationary island or continent changed'
assert np.array_equal(output[edited==0],image[edited==0]),'Pixels outside edits changed'
for c,dx,dy in plans:
    dest=c['points']+np.array([dx,dy])
    rentry=next(e for e in report if e['id']==c['id'])
    assert np.array_equal(output[dest[:,1],dest[:,0]],image[c['points'][:,1],c['points'][:,0]]),'Final moved island RGB changed'
    q,r=rentry['target_hex']
    distances=(LIMITS+cell_center(q,r) @ NORMALS.T-(dest @ NORMALS.T).max(axis=0))/NORM_LENGTHS
    assert distances.min()>=CLEARANCE-1e-6,'Island crosses hex boundary'
destination=DEST/'terrain-map-islands-preview-v2.png'
Image.fromarray(output).save(destination)
summary.update({'output':str(destination.relative_to(ROOT)),
                'output_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
                'changed_pixels':int(np.count_nonzero(np.any(output!=image,axis=2))),
                'validation':{'moved_land_rgb_identical':True,'stationary_land_rgb_identical':True,
                              'outside_edit_regions_identical':True,'all_moved_islands_within_hex':True}})
(DEST/'placement-analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved:',destination)
print('Moved:',len(plans),'; changed pixels:',summary['changed_pixels'])

viewer=(ROOT/'scripts/templates/islands-preview.html').read_text(encoding='utf-8-sig')
movements=[{key:e[key] for key in ('original_center','translation_px','target_hex')} for e in report if e['status']=='moved']
viewer=viewer.replace('__ISLAND_MOVES__',json.dumps(movements,separators=(',',':')))
(DEST/'index.html').write_text(viewer,encoding='utf-8')
print('Comparison viewer saved:',DEST/'index.html')

