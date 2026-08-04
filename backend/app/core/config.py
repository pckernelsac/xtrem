from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Valor de fábrica del SECRET_KEY. Está en el repo, así que arrancar con él en
#: producción permitiría a cualquiera forjar un JWT válido.
SECRET_KEY_POR_DEFECTO = "cambiar-en-produccion"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Zona Xtrema ERP"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Zona horaria del negocio. Los timestamps se guardan en UTC; esto define
    # dónde empieza y termina «el día» en reportes, dashboard y arqueos.
    TIMEZONE: str = "America/Lima"

    # Base de datos
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "zonaxtrema"
    POSTGRES_PASSWORD: str = "zonaxtrema"
    POSTGRES_DB: str = "zonaxtrema"
    #: Conexión completa. Si viene con valor, gana sobre los POSTGRES_* de arriba.
    DATABASE_URL: str = ""

    # Auth
    SECRET_KEY: str = "cambiar-en-produccion"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Enlaces públicos de impresión / compartir por WhatsApp.
    # La URL base debe ser la que ve el cliente desde fuera, no localhost.
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    #: 7 días: el cliente puede abrir el enlace de WhatsApp bastante después
    #: de recibirlo, pero no queda vigente para siempre.
    PRINT_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # Impresora térmica
    TICKET_ANCHO_MM: int = 80
    TICKET_MARGEN_MM: float = 4.0

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173"

    # --- Facturación electrónica ---
    #: Proveedor activo: "nubefact" o "factpro". Se deja conmutable para poder
    #: volver atrás sin desplegar código si el nuevo proveedor falla.
    FACTURADOR: str = "nubefact"

    # --- Nubefact ---
    #: RUTA única del cliente, con su UUID. Las cuatro operaciones van al mismo
    #: sitio por POST; lo que cambia es el campo `operacion` del cuerpo.
    NUBEFACT_RUTA: str = ""
    NUBEFACT_TOKEN: str = ""
    NUBEFACT_TIMEOUT_SEGUNDOS: float = 30.0

    # --- FactPro (proveedor anterior, se conserva para poder volver) ---
    FACTPRO_BASE_URL: str = "https://api.factpro.la/api/v3"
    FACTPRO_TOKEN: str = ""
    # Rutas tomadas de la doc viva (docs.factpro.la), que difieren del prompt.
    # Configurables por si FactPro las cambia sin tocar código.
    FACTPRO_PATH_DOCUMENTOS: str = "/documentos"
    FACTPRO_PATH_ANULAR: str = "/anular"
    FACTPRO_PATH_CONSULTA: str = "/consulta"
    FACTPRO_TIMEOUT_SEGUNDOS: float = 30.0

    # Datos del emisor y series autorizadas. Las series las da de alta el
    # facturador, NO son libres: emitir con una que la cuenta no tenga
    # habilitada se rechaza con "no puedes emitir comprobantes con esta serie".
    # Las cuentas demo de Nubefact traen BBB1 y FFF1; en producción se usan las
    # autorizadas por SUNAT (B001/F001). Nubefact exige 4 caracteres exactos y
    # que empiecen por B (boletas y sus notas) o F (facturas y sus notas).
    EMISOR_RUC: str = "10431869662"
    EMISOR_RAZON_SOCIAL: str = "ZONA XTREMA BIKES & COMPONENTES"
    SERIE_FACTURA: str = "F001"
    SERIE_BOLETA: str = "B001"
    SERIE_NC_FACTURA: str = "FC01"
    SERIE_NC_BOLETA: str = "BC01"
    MONEDA_POR_DEFECTO: str = "PEN"

    # Consulta de RENIEC/SUNAT por documento. Va por APIsPERU, que es un
    # servicio independiente del facturador: si el facturador cae, el
    # autocompletado del mostrador sigue en pie.
    APISPERU_URL: str = "https://dniruc.apisperu.com/api/v1"
    APISPERU_TOKEN: str = ""

    @property
    def usa_nubefact(self) -> bool:
        return self.FACTURADOR.strip().lower() == "nubefact"

    @property
    def consulta_documento_disponible(self) -> bool:
        """Sin token de APIsPERU, el autocompletado por DNI/RUC no opera.

        Mira **sólo** el token de APIsPERU, que es el único servicio que
        consulta `consulta_documento.py`. Aceptar aquí el token viejo de FactPro
        haría que el botón "Buscar" apareciera y luego fallara en la llamada.
        """
        return bool(self.APISPERU_TOKEN.strip())

    @property
    def factpro_simulado(self) -> bool:
        """Sin credenciales no se llama a SUNAT: se opera en modo simulación.

        Permite construir y persistir comprobantes con la misma estructura que
        los reales para desarrollar y demostrar el flujo completo. Poner las
        credenciales reales conmuta a la emisión efectiva sin más cambios.

        El nombre se conserva porque lo consumen el endpoint de conteos y el
        frontend; lo que decide es el proveedor activo.
        """
        if self.usa_nubefact:
            return not (self.NUBEFACT_RUTA.strip() and self.NUBEFACT_TOKEN.strip())
        return not self.FACTPRO_TOKEN.strip()

    @property
    def database_url(self) -> str:
        """Cadena de conexión, con `DATABASE_URL` teniendo prioridad.

        En desarrollo se arma con las piezas sueltas (`POSTGRES_*`), que es lo
        que expone el compose local. En Dokploy la base es un servicio aparte y
        lo que se entrega es una URL completa, así que ésa manda si está puesta.

        Se normaliza el esquema a `postgresql+psycopg`: los paneles suelen dar
        `postgresql://` o `postgres://`, y SQLAlchemy elegiría psycopg2, que no
        está instalado.
        """
        if self.DATABASE_URL.strip():
            url = self.DATABASE_URL.strip()
            for prefijo in ("postgresql+psycopg://", "postgresql://", "postgres://"):
                if url.startswith(prefijo):
                    return "postgresql+psycopg://" + url[len(prefijo) :]
            return url

        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def es_desarrollo(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in ("development", "dev", "local", "test")

    @model_validator(mode="after")
    def _exigir_secret_seguro(self) -> "Settings":
        """Fuera de desarrollo, no se arranca con un SECRET_KEY débil o de fábrica.

        Con el valor por defecto (público) o una clave demasiado corta, cualquiera
        podría firmar un JWT y entrar como cualquier usuario. Es preferible que el
        despliegue falle en el arranque a que corra abierto sin que nadie lo note.
        """
        if self.es_desarrollo:
            return self
        clave = self.SECRET_KEY.strip()
        if clave == SECRET_KEY_POR_DEFECTO or len(clave) < 32:
            raise ValueError(
                "SECRET_KEY inseguro para producción: define uno propio de al menos "
                "32 caracteres (p. ej. `openssl rand -hex 32`)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
