import numpy as np

from agroscore.zones import kmeans_1d, zonificar


def test_kmeans_ordena_por_media():
    v = np.r_[np.full(50, 0.3), np.full(30, 0.6), np.full(20, 0.9)]
    etq, centros = kmeans_1d(v)
    assert list(centros) == sorted(centros)
    assert (etq[:50] == 0).all() and (etq[-20:] == 2).all()


def test_zonificar_pct_suman_100_y_respeta_nan():
    rng = np.random.default_rng(1)
    a = rng.uniform(0.5, 0.9, (40, 40))
    a[:5] = np.nan
    z = zonificar(a)
    assert z["alta_pct"] + z["media_pct"] + z["baja_pct"] == 100
    assert (z["mapa"][:5] == -1).all()


def test_zonificar_sin_pixeles():
    z = zonificar(np.full((4, 4), np.nan))
    assert z["alta_pct"] is None
