import json,sys
A,B='out_gee_full','out_gee_v12'
obs11=json.load(open(f'{B}/_obs_validas_px_v11.json'))
lotes=['ejemplo_roca_norte','ejemplo_roca_sur','ejemplo_rio_cuarto_este']
L=lambda d,i: json.load(open(f'{d}/{i}/lote.json'))
out=[]
P=out.append
P('## Resumen por lote (antes = out_gee_full, v1.1.0; después = out_gee_v12, v1.2.0)\n')
P('| Lote | Score antes→después | Vigor | Estabilidad | Riesgo hídrico | Suelo | Rotación | Ha anegadas (conf.) antes→después | S1 sin confirmar (después) | NDVI máx (máx. entre campañas) antes→después | EVI máx (máx. entre campañas) | vigor_base |')
P('|---|---|---|---|---|---|---|---|---|---|---|---|')
for i in lotes:
    a,b=L(A,i),L(B,i)
    ca={c['clave']:c['valor'] for c in a['score']['componentes']}; cb={c['clave']:c['valor'] for c in b['score']['componentes']}
    f=lambda k: f"{ca[k]}→{cb[k]}"
    na=max(c['ndvi_max'] for c in a['campanias']); nb=max(c['ndvi_max'] for c in b['campanias'])
    ev=[c['evi_max'] for c in b['campanias']]; 
    P(f"| {i} | {a['score']['valor']}→{b['score']['valor']} | {f('vigor_historico')} | {f('estabilidad')} | {f('riesgo_hidrico')} | {f('suelo')} | {f('rotacion_mani')} | {a['agua']['max_ha_anegadas']}→{b['agua']['max_ha_anegadas']} | {b['agua']['max_ha_s1_sin_confirmar']} ({b['agua']['fecha_max_s1_sin_confirmar']}) | {na}→{nb} | {max(ev)} (mín {min(ev)}) | {b['score']['vigor_base']} |")
P('\n## Agua: auditoría del descarte (después)\n')
P('| Lote | Escenas S1 | con óptico | marcadas (≥5 % del lote) | marcadas sin poder contrastar | escenas con anegamiento confirmado | frecuencia JRC % |')
P('|---|---|---|---|---|---|---|')
for i in lotes:
    g=L(B,i)['agua']; P(f"| {i} | {g['n_escenas_s1']} | {g['n_escenas_s1_con_optico']} | {g.get('n_escenas_s1_marcadas')} | {g.get('n_escenas_s1_marcadas_sin_optico')} | {g.get('n_escenas_s1_confirmadas')} | {g['frecuencia_pct']} |")
P('\n## Por campaña (antes→después): n_escenas, % nubes, obs. válidas medias por píxel (v1.1 máscara vieja → v1.2 Cloud Score+), NDVI máx, EVI máx, NDRE máx (nuevo)\n')
for i in lotes:
    a,b=L(A,i),L(B,i)
    P(f'**{i}**\n'); P('| Campaña | n_escenas | % nubes | obs/px | NDVI máx | EVI máx | NDRE máx |'); P('|---|---|---|---|---|---|---|')
    for ca,cb in zip(a['campanias'],b['campanias']):
        c=cb['campania']
        P(f"| {c} | {ca['n_escenas']}→{cb['n_escenas']} | {ca['pct_nubes']}→{cb['pct_nubes']} | {obs11[i][c]}→{cb['obs_validas_px']} | {ca['ndvi_max']}→{cb['ndvi_max']} | {cb['evi_max']} | {cb['ndre_max']} |")
    P('')
P('## Sensibilidad del vigor a las referencias de EVI (PROVISORIAS; misma salida, solo recalculando el componente)\n')
refs=[(0.30,0.75),(0.30,0.85),(0.30,0.90),(0.40,0.90),(0.20,0.80)]
P('| Lote | EVI máx medio | '+' | '.join(f'ref {a}–{b}' for a,b in refs)+' |'); P('|---|---|'+'---|'*len(refs))
import statistics
for i in lotes:
    v=[c['evi_max'] for c in L(B,i)['campanias']]; m=statistics.fmean(v)
    P(f"| {i} | {m:.3f} | "+' | '.join(f"{max(0,min(1,(m-a)/(b-a))):.2f}" for a,b in refs)+' |')
open(f'{B}/comparacion_v11_v12.md','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
