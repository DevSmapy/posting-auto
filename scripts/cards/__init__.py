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
from .infographic import (
    PictogramMatch,
    build_infographic_fields,
    export_infographic,
    load_catalog,
    render_infographic_html,
    resolve_pictogram,
    resolve_pictograms,
    validate_visual_tags,
    visual_tag_options,
)
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
    "PictogramMatch",
    "Slide",
    "SlideType",
    "TemplateBundle",
    "build_infographic_fields",
    "export_infographic",
    "get_bundle",
    "list_bundles",
    "load_catalog",
    "load_design_guide",
    "placeholder_content",
    "recommend_for_economy_society",
    "render_infographic_html",
    "resolve_pictogram",
    "resolve_pictograms",
    "validate_visual_tags",
    "visual_tag_options",
]
