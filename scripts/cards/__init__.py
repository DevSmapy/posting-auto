"""Card news format: slides + Instagram caption assembly and local export."""

from .assembler import CardAssembler
from .bundles import (
    TemplateBundle,
    get_bundle,
    list_bundles,
    load_design_guide,
    recommend_for_economy_society,
)
from .caption import InstagramCaptionBuilder
from .config import CardFormatConfig
from .copy import CardCopyRules
from .models import CardBundle, InstagramPost, Slide, SlideType
from .editorial import EditorialCarouselTemplate, placeholder_content
from .narrative import NarrativeAssembler
from .renderer import CardRenderer, CardTemplateRenderer

__all__ = [
    "CardAssembler",
    "CardBundle",
    "CardCopyRules",
    "CardFormatConfig",
    "CardRenderer",
    "CardTemplateRenderer",
    "EditorialCarouselTemplate",
    "InstagramCaptionBuilder",
    "InstagramPost",
    "NarrativeAssembler",
    "Slide",
    "SlideType",
    "TemplateBundle",
    "get_bundle",
    "list_bundles",
    "load_design_guide",
    "placeholder_content",
    "recommend_for_economy_society",
]
