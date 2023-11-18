{
  # nixpkgs 23.05, deterministic. Last updated: 2023-06-03.
  pkgs ? import (fetchTarball("https://github.com/NixOS/nixpkgs/archive/f3d743463920751eb092930d06e700981398332a.tar.gz")) {}
}:

with pkgs;
let
  my-python-packages = python-packages: with python-packages; [
    coloredlogs
    black
    pyqt5
  ];
  python-with-my-packages = python310.withPackages my-python-packages;
in
mkShell rec {
  nativeBuildInputs = with pkgs; [
    libsForQt5.wrapQtAppsHook
    makeWrapper
  ];
  buildInputs = [
    python-with-my-packages
    adwaita-qt
    jetbrains.pycharm-community
    poetry
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
