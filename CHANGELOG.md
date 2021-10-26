# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## 1.1.0 - 2021-10-26

### Added

- Support custom encoding/decoding implementation via the `packb=...` and `unpackb=...` optional parameters, allowing the use of alternative msgpack libraries. (Pull #20)

### Fixed

- Properly re-write request `Content-Type` to `application/json`. (Pull #24)

## 1.0.0 - 2020-03-26

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
