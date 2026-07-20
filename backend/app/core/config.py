from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # --- FactPro / facturación electrónica (Fase 6) ---
    FACTPRO_BASE_URL: str = "https://api.factpro.la/api/v3"
    FACTPRO_TOKEN: str = ""
    # Rutas tomadas de la doc viva (docs.factpro.la), que difieren del prompt.
    # Configurables por si FactPro las cambia sin tocar código.
    FACTPRO_PATH_DOCUMENTOS: str = "/documentos"
    FACTPRO_PATH_ANULAR: str = "/anular"
    FACTPRO_PATH_CONSULTA: str = "/consulta"
    FACTPRO_TIMEOUT_SEGUNDOS: float = 30.0

    # Datos del emisor y series autorizadas por SUNAT (se configuran en FactPro).
    EMISOR_RUC: str = "10431869662"
    EMISOR_RAZON_SOCIAL: str = "ZONA XTREMA BIKES & COMPONENTES"
    FACTPRO_SERIE_FACTURA: str = "F001"
    FACTPRO_SERIE_BOLETA: str = "B001"
    FACTPRO_SERIE_NC_FACTURA: str = "FC01"
    FACTPRO_SERIE_NC_BOLETA: str = "BC01"
    MONEDA_POR_DEFECTO: str = "PEN"

    # Consulta de RENIEC/SUNAT por documento (producto aparte de FactPro,
    # con su propio token; base y token distintos a los de facturación).
    FACTPRO_CONSULTAS_URL: str = "https://consultas.factpro.la/api/v1"
    FACTPRO_CONSULTAS_TOKEN: str = ""

    @property
    def consulta_documento_disponible(self) -> bool:
        """Sin token de consultas, el autocompletado por DNI/RUC no opera."""
        return bool(self.FACTPRO_CONSULTAS_TOKEN.strip())

    @property
    def factpro_simulado(self) -> bool:
        """Sin token no se llama a SUNAT: se opera en modo simulación.

        Permite construir y persistir comprobantes con la misma estructura que
        los reales para desarrollar y demostrar el flujo completo. Poner el
        token real conmuta a la emisión efectiva sin más cambios.
        """
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
