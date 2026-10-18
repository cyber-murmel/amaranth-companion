let
  pkgs_rev = "21691b79c41ba30a80b110523c943d8d45a0912b";
in
{
  # nixpkgs 23.05, deterministic. Last updated: 2023-06-03.
  pkgs ? import (fetchTarball("https://github.com/NixOS/nixpkgs/archive/${pkgs_rev}.tar.gz")) {
    config.allowUnfree = true;
  }
}:

with pkgs;
let
  my-python-packages = python-packages: with python-packages; [
    coloredlogs
    black
    pyqt5
    pytest
  ];
  python-with-my-packages = python314.withPackages my-python-packages;
in
mkShell rec {
  nativeBuildInputs = with pkgs; [
    libsForQt5.wrapQtAppsHook
    makeWrapper
  ];
  buildInputs = [
    python-with-my-packages
    uv
    adwaita-qt
    jetbrains.pycharm
    umlet
  ];
  # https://discourse.nixos.org/t/python-qt-woes/11808/10
  shellHook = ''
    setQtEnvironment=$(mktemp --suffix .setQtEnvironment.sh)
    echo "shellHook: setQtEnvironment = $setQtEnvironment"
    makeWrapper "/bin/sh" "$setQtEnvironment" "''${qtWrapperArgs[@]}"
    sed "/^exec/d" -i "$setQtEnvironment"
    source "$setQtEnvironment"
  '';
}
