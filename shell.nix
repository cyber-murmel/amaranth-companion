let
  pkgs_rev = "21691b79c41ba30a80b110523c943d8d45a0912b"; # nixpkgs 26.05, deterministic.
in
{
  pkgs ? import (fetchTarball("https://github.com/NixOS/nixpkgs/archive/${pkgs_rev}.tar.gz")) {
    config.allowUnfree = true;
  }
}:

with pkgs;
let
  # The Glasgow platform lives in the `glasgow` package, which nixpkgs ships
  # as an application -- `buildPythonApplication` deliberately hides the
  # importable module, and `toPythonModule` puts it back. It is built for the
  # default `python3`, so it is rebuilt here for the one this shell uses;
  # without that the module lands in the wrong site-packages and the editor
  # reports the board as not installed. `doCheck = false` skips glasgow's own
  # test suite, which is not what we are testing.
  glasgow-module = python314Packages.toPythonModule (
    (glasgow.override { python3 = python314; }).overridePythonAttrs (_: {
      doCheck = false;
    })
  );

  my-python-packages = python-packages: (with python-packages; [
    amaranth
    amaranth-boards
    coloredlogs
    black
    pyqt5
    pyyaml
    pytest
    pytest-cov
  ]) ++ [ glasgow-module ];
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
    # formal verification. These are applications, not python modules:
    # withPackages silently drops `sby`, and only `yosys` happens to resolve
    # through python314Packages.
    yosys
    sby
    # sby shells out to a solver; without one, `prove` and `bmc` cannot run
    z3
    boolector
    # waveform viewer, plus the vcd2fst it ships with
    gtkwave
    # synthesis and place-and-route, for building bitstreams. yosys above is
    # shared with the formal flow.
    nextpnr
    icestorm
    trellis
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
