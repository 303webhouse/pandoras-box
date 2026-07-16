"""Tool implementations.

Importing this package side-effect-registers every tool with the
decorator registry. The router reads the registry at startup to build
the FastMCP tool list.
"""

from . import bias_composite as _bias  # noqa: F401
from . import flow_radar as _flow  # noqa: F401
from . import sector_strength as _sector  # noqa: F401
from . import hermes_alerts as _hermes  # noqa: F401
from . import hydra_scores as _hydra  # noqa: F401
from . import positions as _positions  # noqa: F401
from . import portfolio_balances as _balances  # noqa: F401
from . import quote as _quote  # noqa: F401
from . import crypto_quote as _crypto_quote  # noqa: F401
from . import options_chain as _options_chain  # noqa: F401
from . import trade_ideas as _trade_ideas  # noqa: F401
from . import market_profile as _market_profile  # noqa: F401
from . import chart_indicators as _chart_indicators  # noqa: F401
from . import ping as _ping  # noqa: F401
from . import describe as _describe  # noqa: F401
from . import stable_regime as _stable_regime  # noqa: F401
from . import stable_themes as _stable_themes  # noqa: F401
from . import stable_theme_members as _stable_theme_members  # noqa: F401
from . import stable_movers as _stable_movers  # noqa: F401
from . import stable_rates_fx as _stable_rates_fx  # noqa: F401
from . import board_state as _board_state  # noqa: F401
from . import crypto_market_profile as _crypto_market_profile  # noqa: F401
