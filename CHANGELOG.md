# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## 1.0.0 - 2020-26-03

_First production/stable release._

### Changed

- Switch to private module naming. Components should now be imported from the root package, e.g. `from msgpack_asgi import MessagePackMiddleware`. (Pull #5)

### Fixed

- Add missing `MANIFEST.in`. (Pull #4)

## 0.1.0 - 2019-11-04

Initial release.

### Added

- Add the `MessagePackMiddleware` ASGI middleware.
- Add the `MessagePackResponse` ASGI response class.
