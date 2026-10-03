#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Bootstrap dependencies once with `devenv shell -- true`; runs stay offline.
if [[ ${FINNISH_TEXT_DEVENV:-} != 1 ]]; then
  exec devenv --offline --no-tui shell -- bash autoresearch.sh "$@"
fi

export LC_ALL=C.UTF-8
export SOURCE_DATE_EPOCH=0
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export UV_OFFLINE=1
unset VOIKKO_DICTIONARY_PATH
root=$PWD
build="$root/.bench-build"
mkdir -p "$build/library" "$build/vvfst" "$build/dictionaries"

# Rebuild source changes; fixed toolchain/configuration, no downloaded dictionary.
if [[ ! -f libvoikko/configure || libvoikko/configure.ac -nt libvoikko/configure || libvoikko/Makefile.am -nt libvoikko/configure || libvoikko/src/Makefile.am -nt libvoikko/configure ]]; then
  (cd libvoikko && autoreconf --force --install) >"$build/autoreconf.log" 2>&1 || { cat "$build/autoreconf.log"; exit 1; }
fi
if [[ ! -f "$build/library/Makefile" || libvoikko/configure -nt "$build/library/Makefile" ]]; then
  (cd "$build/library" && "$root/libvoikko/configure" --disable-hfst --disable-external-dicts CXX=clang++ CXXFLAGS='-O2 -g0') >"$build/configure.log" 2>&1 || { cat "$build/configure.log"; exit 1; }
fi
make -C "$build/library" -j4 >"$build/library.log" 2>&1 || { cat "$build/library.log"; exit 1; }
export PATH="$build/library/src/tools:$PATH"
make -C voikko-fi vvfst-install "VVFST_BUILDDIR=$build/vvfst" "DESTDIR=$build/dictionaries" 'PYTHON=uv run --offline --no-project --no-python-downloads' >"$build/dictionary.log" 2>&1 || { cat "$build/dictionary.log"; exit 1; }

uv run --offline --no-project --no-python-downloads benchmarks/check_finnish.py \
  --library "$build/library/src/.libs" \
  --dictionary "$build/dictionaries" \
  --report "$build/findings.json" "$@"
