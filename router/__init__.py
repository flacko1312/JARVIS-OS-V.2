"""router — Sistema de enrutamiento de JARVIS.

Clasifica intención del usuario y delega al handler correcto.
"""
from router.classifier import classify
from router.models import Domain, RouteResult
from router.core import JarvisRouter

__all__ = ["classify", "Domain", "RouteResult", "JarvisRouter"]
