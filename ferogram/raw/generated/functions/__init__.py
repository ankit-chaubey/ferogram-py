# Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# ferogram is a high-performance Telegram MTProto framework written in Rust.
# ferogram-py provides Python bindings built on top of the Rust core for
# building Telegram clients, bots, and applications with a simple API.
#
# Rust core: https://github.com/ankit-chaubey/ferogram
# Python bindings: https://github.com/ankit-chaubey/ferogram-py
#
# If you use or modify this code, keep this notice at the top of the file
# and include the LICENSE-MIT or LICENSE-APACHE file from this repository.


# auto-generated - do not edit
# Flat imports so both styles work:
#   raw.functions.messages.GetHistory(...)   ← namespace style
#   raw.functions.GetHistory(...)            ← flat style (convenience)

from .account import *  # noqa: F401,F403
from .auth import *  # noqa: F401,F403
from .bots import *  # noqa: F401,F403
from .channels import *  # noqa: F401,F403
from .chatlists import *  # noqa: F401,F403
from .contacts import *  # noqa: F401,F403
from .folders import *  # noqa: F401,F403
from .fragment import *  # noqa: F401,F403
from .help import *  # noqa: F401,F403
from .langpack import *  # noqa: F401,F403
from .messages import *  # noqa: F401,F403
from .payments import *  # noqa: F401,F403
from .phone import *  # noqa: F401,F403
from .photos import *  # noqa: F401,F403
from .premium import *  # noqa: F401,F403
from .smsjobs import *  # noqa: F401,F403
from .stats import *  # noqa: F401,F403
from .stickers import *  # noqa: F401,F403
from .stories import *  # noqa: F401,F403
from .updates import *  # noqa: F401,F403
from .upload import *  # noqa: F401,F403
from .users import *  # noqa: F401,F403

# namespace sub-modules
from . import account  # noqa: F401
from . import auth  # noqa: F401
from . import bots  # noqa: F401
from . import channels  # noqa: F401
from . import chatlists  # noqa: F401
from . import contacts  # noqa: F401
from . import folders  # noqa: F401
from . import fragment  # noqa: F401
from . import help  # noqa: F401
from . import langpack  # noqa: F401
from . import messages  # noqa: F401
from . import payments  # noqa: F401
from . import phone  # noqa: F401
from . import photos  # noqa: F401
from . import premium  # noqa: F401
from . import smsjobs  # noqa: F401
from . import stats  # noqa: F401
from . import stickers  # noqa: F401
from . import stories  # noqa: F401
from . import updates  # noqa: F401
from . import upload  # noqa: F401
from . import users  # noqa: F401
