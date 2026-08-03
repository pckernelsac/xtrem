"""PDF del arqueo de una jornada de caja.

El reporte que se imprime al cerrar el día: cuánto entró por cada método, el
cuadre del cajón físico y el detalle de movimientos. Reutiliza la maquinaria
del PDF de la ficha (entorno Jinja, assets embebidos, formato de importes) en
vez de duplicarla.
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from weasyprint import HTML

from app.models.caja import ETIQUETAS_METODO, MetodoPago, SesionCaja
from app.services.ficha_pdf import BASE_DIR, EMPRESA, _asset_data_url, _env, _monto

LIMA = ZoneInfo("America/Lima")

CERO = Decimal("0.00")


def _fecha(dt: datetime | None) -> str:
    return dt.astimezone(LIMA).strftime("%d/%m/%Y %I:%M %p") if dt else ""


def _filas_metodos(totales: dict[str, dict[str, Decimal]]) -> list[dict[str, object]]:
    """Un renglón por método que se haya movido.

    Los que quedaron en cero se omiten: en un reporte impreso, cuatro filas de
    S/ 0.00 sólo estorban a quien busca lo que sí se cobró.
    """
    filas = []
    for metodo in MetodoPago:
        t = totales.get(metodo.value, {})
        ingresos = Decimal(t.get("ingresos", CERO))
        egresos = Decimal(t.get("egresos", CERO))
        if ingresos == CERO and egresos == CERO:
            continue
        filas.append(
            {
                "label": ETIQUETAS_METODO[metodo.value],
                "ingresos": _monto(ingresos),
                "egresos": _monto(egresos) if egresos else "",
                "neto": _monto(ingresos - egresos),
                "es_efectivo": metodo is MetodoPago.EFECTIVO,
            }
        )
    return filas


def render_arqueo_pdf(
    sesion: SesionCaja,
    totales: dict[str, dict[str, Decimal]],
    esperado: Decimal,
    cantidad_ventas: int,
) -> bytes:
    """Hoja A4 del arqueo. `esperado` se calcula fuera porque necesita la BD."""
    efectivo = totales.get(MetodoPago.EFECTIVO.value, {})
    ingresos_efectivo = Decimal(efectivo.get("ingresos", CERO))
    egresos_efectivo = Decimal(efectivo.get("egresos", CERO))

    ingresos_total = sum(
        (Decimal(t.get("ingresos", CERO)) for t in totales.values()), CERO
    )
    egresos_total = sum((Decimal(t.get("egresos", CERO)) for t in totales.values()), CERO)

    # El fondo de apertura no es una venta: queda fuera del total cobrado y
    # sólo aparece en el cuadre del cajón, que es donde sí cuenta.
    cerrada = sesion.monto_declarado is not None
    diferencia = sesion.diferencia

    contexto = {
        "empresa": EMPRESA,
        "logo": _asset_data_url("logo_zonaxtrema.png"),
        "s": sesion,
        "estado_label": "Cerrada" if cerrada else "Abierta",
        "apertura": _fecha(sesion.fecha_apertura),
        "cierre": _fecha(sesion.fecha_cierre),
        "usuario_apertura": sesion.usuario_apertura.full_name if sesion.usuario_apertura else "",
        "usuario_cierre": sesion.usuario_cierre.full_name if sesion.usuario_cierre else "",
        "metodos": _filas_metodos(totales),
        "ingresos_total": _monto(ingresos_total),
        "egresos_total": _monto(egresos_total) if egresos_total else "",
        "total_cobrado": _monto(ingresos_total - egresos_total),
        "cuadre": {
            "fondo": _monto(sesion.monto_inicial),
            "ingresos": _monto(ingresos_efectivo),
            "egresos": _monto(egresos_efectivo),
            "tiene_egresos": egresos_efectivo > CERO,
            # Cerrada la jornada manda el esperado congelado: si después se
            # anuló una venta de ese día, el arqueo firmado no debe moverse.
            "esperado": _monto(
                sesion.monto_esperado if sesion.monto_esperado is not None else esperado
            ),
            "contado": _monto(sesion.monto_declarado) if cerrada else "",
            "diferencia": _monto(diferencia) if diferencia is not None else "",
            "cuadra": diferencia is not None and abs(diferencia) < Decimal("0.01"),
            "sobra": diferencia is not None and diferencia > CERO,
        },
        "cerrada": cerrada,
        "cantidad_ventas": cantidad_ventas,
        "movimientos": [
            {
                "hora": m.created_at.astimezone(LIMA).strftime("%I:%M %p"),
                "metodo": ETIQUETAS_METODO[m.metodo.value],
                "concepto": m.concepto,
                "usuario": m.usuario.full_name if m.usuario else "",
                "ingreso": m.tipo.value == "INGRESO",
                "monto": _monto(m.monto),
            }
            for m in sesion.movimientos
        ],
        "impreso": _fecha(datetime.now(LIMA)),
    }

    html = _env().get_template("arqueo.html").render(**contexto)
    return HTML(string=html, base_url=str(BASE_DIR)).write_pdf()
