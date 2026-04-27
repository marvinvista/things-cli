# Install things-cli

`things-cli` is designed to be installed with `pipx` on macOS. `pipx` keeps the CLI in its own isolated Python environment and exposes the `things` command on your shell path.

## Install pipx

```sh
brew install pipx
pipx ensurepath
```

Open a new terminal after `pipx ensurepath` if your shell cannot find newly installed commands.

## Install From GitHub

After this repository is pushed to GitHub, users can install it with:

```sh
pipx install git+https://github.com/marvinvista/things-cli.git
```

Then verify:

```sh
things diagnose
things list --list Today --limit 5
```

## Install From a Local Clone

```sh
git clone https://github.com/marvinvista/things-cli.git
cd things-cli
pipx install .
```

For development, reinstall after local changes:

```sh
pipx install --force .
```

## Uninstall

```sh
pipx uninstall things-cli
```

## macOS Permissions

The first live command may trigger a macOS Automation permission prompt. Grant your terminal permission to control Things.

If needed, check:

`System Settings -> Privacy & Security -> Automation`
