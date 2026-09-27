"""Reflex configuration.

Any value here can be overridden with a ``REFLEX_``-prefixed environment
variable, e.g. ``REFLEX_API_URL=https://chat.example.com`` when the app sits
behind a reverse proxy on a different host or port.
"""

import reflex as rx

config = rx.Config(
    app_name="chatbot",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(
            theme=rx.theme(appearance="inherit", accent_color="violet", radius="large"),
        ),
    ],
)
