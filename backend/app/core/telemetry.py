from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
import os

def setup_telemetry(app, engine):
    """
    Initialize OpenTelemetry. Call this ONCE in main.py at startup.
    Requires OTEL_EXPORTER_OTLP_ENDPOINT env var (e.g. http://otel-collector:4317)
    """
    # Only enable telemetry if the endpoint is provided in the environment
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        import logging
        logging.getLogger(__name__).info("OpenTelemetry not configured (OTEL_EXPORTER_OTLP_ENDPOINT missing). Skipping telemetry setup.")
        return

    provider = TracerProvider()
    exporter = OTLPSpanExporter()  # reads OTEL_EXPORTER_OTLP_ENDPOINT from env
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI (every route gets traced automatically)
    FastAPIInstrumentor.instrument_app(app)
    
    # Auto-instrument SQLAlchemy (every DB query gets traced)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
