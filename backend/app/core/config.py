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

    # --- Facturación electrónica: emisión propia ante SUNAT ---
    # Se emite directo, sin PSE: el XML se firma aquí con el certificado de la
    # empresa y se manda a SUNAT. La clave privada no sale de este servidor.
    #
    # Ruta al certificado digital (.pfx/.p12) DENTRO del contenedor, montado
    # como volumen o secreto. Nunca en la imagen ni en el repositorio.
    CERTIFICADO_RUTA: str = "/certs/certificado.pfx"
    CERTIFICADO_CLAVE: str = ""
    #: Usuario SOL **secundario**, no el principal. Se revoca sin tocar el otro.
    SOL_USUARIO: str = ""
    SOL_CLAVE: str = ""
    #: False apunta al ambiente de pruebas: los documentos NO tienen validez.
    SUNAT_PRODUCCION: bool = False

    # Datos del emisor, que van dentro del XML y deben coincidir con el padrón.
    EMISOR_RUC: str = "10431869662"
    EMISOR_RAZON_SOCIAL: str = "ZONA XTREMA BIKES & COMPONENTES"
    EMISOR_NOMBRE_COMERCIAL: str = ""
    EMISOR_UBIGEO: str = "120101"
    EMISOR_DIRECCION: str = "Av. San Carlos N° 177"
    EMISOR_DEPARTAMENTO: str = "JUNIN"
    EMISOR_PROVINCIA: str = "HUANCAYO"
    EMISOR_DISTRITO: str = "HUANCAYO"

    # Series autorizadas por SUNAT. Cuatro caracteres, empezando por F para
    # facturas y sus notas, y por B para boletas y las suyas.
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
    def consulta_documento_disponible(self) -> bool:
        """Sin token de APIsPERU, el autocompletado por DNI/RUC no opera."""
        return bool(self.APISPERU_TOKEN.strip())

    @property
    def facturacion_simulada(self) -> bool:
        """Sin certificado ni credenciales SOL no se llama a SUNAT.

        Permite construir y persistir comprobantes con la misma estructura que
        los reales para desarrollar y demostrar el flujo completo. Configurar el
        certificado y el usuario SOL conmuta a la emisión efectiva sin más
        cambios de código.
        """
        return not (
            self.CERTIFICADO_CLAVE.strip()
            and self.SOL_USUARIO.strip()
            and self.SOL_CLAVE.strip()
        )

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
