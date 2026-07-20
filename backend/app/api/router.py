from fastapi import APIRouter

from app.api.routes import (
    auth,
    bicicletas,
    caja,
    clientes,
    facturacion,
    fichas,
    inventario,
    reportes,
    roles,
    sistema,
    users,
    ventas,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(clientes.router)
api_router.include_router(bicicletas.router)
api_router.include_router(fichas.router)
api_router.include_router(inventario.router)
api_router.include_router(ventas.router)
api_router.include_router(caja.router)
api_router.include_router(facturacion.router)
api_router.include_router(reportes.router)
api_router.include_router(sistema.router)
