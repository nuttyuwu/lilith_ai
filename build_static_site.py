import os
import shutil

from flask import Flask, render_template

# Flask needs an app context to use render_template for Jinja output.
app = Flask(__name__, template_folder="templates", static_folder="static")


def build():
    os.makedirs("public", exist_ok=True)

    # Render template without sensitive debug/persona data for the public build.
    with app.app_context():
        html = render_template(
            "index.html",
            persona=None,
            memory=[],
            debug=None,
        )

    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    # Copy static assets
    static_src = os.path.join(app.root_path, "static")
    static_dest = os.path.join("public", "static")
    if os.path.exists(static_dest):
        shutil.rmtree(static_dest)
    shutil.copytree(static_src, static_dest)

    api_base = os.getenv("API_BASE_URL", "").rstrip("/")
    if api_base:
        config_path = os.path.join(static_dest, "config.js")
        with open(config_path, "w", encoding="utf-8") as cfg:
            cfg.write(
                "// Auto-generated during build_static_site.py\n"
                f"window.API_BASE_URL = \"{api_base}\";\n"
            )


if __name__ == "__main__":
    build()
