import typer

app = typer.Typer(
    name="pywrangler",
    help="A CLI tool for Cloudflare Workers.",
    add_completion=False,
    no_args_is_help=True  # Ensure help is shown if no command is given
)

@app.command()
def sync():
    """Installs the Python packages specified in the pyproject.toml file into src/vendor and into a .venv-workers virtual env."""
    print("Sync command called (stub).")

@app.command()
def other():
    print("Just here to make sync work")

if __name__ == "__main__":
    app()