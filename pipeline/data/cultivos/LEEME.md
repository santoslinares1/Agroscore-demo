# Mapas de cultivo por campaña (IDECOR)

Dejá acá los GeoTIFF de cultivos de verano de IDECOR con el nombre
`idecor_AAAA-AA.tif` (ej.: `idecor_2024-25.tif`). Requiere `pip install rasterio`.

Antes de usarlos:
1. Los códigos de clase **cambian entre ediciones**: están por campaña en `IDECOR_CLASES_POR_CAMPANIA`
   (`agroscore/config.py`), verificados contra los servicios OGC de IDECOR. Maní solo se separa en 2017/18 (clase 18)
   y 2023/24 en adelante (clase 4). Si una campaña no figura ahí, el archivo se ignora (no se inventan códigos).
   Una clase donde el maní no se puede separar (ej. `otros_posible_mani` en 2022/23) cuenta como "sin dato" de maní.
2. Revisá la licencia de uso (atribución / uso comercial) y anotala en el README.

Si no hay archivo para una campaña, el pipeline prueba MapBiomas (respaldo) y si
tampoco hay dato deja `cultivo: null` con una advertencia.
