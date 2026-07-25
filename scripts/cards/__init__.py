"""Card news format: slides + Instagram caption assembly and local export."""

from .assembler import CardAssembler
from .caption import InstagramCaptionBuilder
from .config import CardFormatConfig
from .copy import CardCopyRules
from .models import CardBundle, InstagramPost, Slide, SlideType
from .renderer import CardRenderer, CardTemplateRenderer

__all__ = [
    "CardAssembler",
    "CardBundle",
    "CardCopyRules",
    "CardFormatConfig",
    "CardRenderer",
    "CardTemplateRenderer",
    "InstagramCaptionBuilder",
    "InstagramPost",
    "Slide",
    "SlideType",
]
