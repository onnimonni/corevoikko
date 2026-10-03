{ pkgs, ... }:
{
  packages = with pkgs; [
    autoconf
    automake
    libtool
    pkg-config
    foma
    gnumake
    coreutils
    clang
    python3
    uv
  ];
  env.FINNISH_TEXT_DEVENV = "1";
}
