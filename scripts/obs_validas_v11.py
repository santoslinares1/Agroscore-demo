"""Reproduce la máscara v1.1.0 (s2cloudless prob<40 + SCL 4,5,6,7,11) solo para contar observaciones válidas por píxel."""
import sys,json
sys.path.insert(0,'.')
import ee
from agroscore import aoi,config,gee
gee.inicializar("digimat-434101")
res={}
for l in aoi.cargar('data/lotes.geojson'):
    g=gee.geometria(l); res[l.id]={}
    for c in config.campanias():
        i,f=config.campania_fechas(c)
        s2=ee.ImageCollection(config.S2_COLECCION).filterBounds(g).filterDate(i,f).filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE",config.S2_MAX_NUBES_ESCENA))
        pr=ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY").filterBounds(g).filterDate(i,f)
        un=ee.Join.saveFirst("cloud_prob").apply(primary=s2,secondary=pr,condition=ee.Filter.equals(leftField="system:index",rightField="system:index"))
        def m(img):
            v=img.select("SCL").remap([4,5,6,7,11],[1]*5,0).And(ee.Image(img.get("cloud_prob")).select("probability").lt(40))
            return img.normalizedDifference(["B8","B4"]).rename("NDVI").updateMask(v)
        col=ee.ImageCollection(un).map(m)
        r=col.select("NDVI").count().reduceRegion(ee.Reducer.mean(),g,10,maxPixels=1e9).getInfo()
        res[l.id][c]=round(r["NDVI"],1)
    print(l.id,res[l.id],flush=True)
json.dump(res,open('out_gee_v12/_obs_validas_px_v11.json','w'),indent=1)
