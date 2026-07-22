#!/usr/bin/env bash
# Back-compat shim — prefer scripts/draft_lifecycle.sh
# shellcheck shell=bash
# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/draft_lifecycle.sh"
