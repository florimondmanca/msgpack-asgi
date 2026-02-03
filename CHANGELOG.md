# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## 3.0.0 - 2026-02-03

### Removed

* Drop official support for Python 3.9 as it has reached EOL. (Pull #35)

### Added

* Add official support for Python 3.14. (Pull #35)
* Add naive buffered request and response streaming, opt-in via `allow_naive_streaming=True`. (Pull #33, #34)

### Fixed

* Fix handling of non-`http.request` ASGI messages when receiving the request (including `http.disconnect`). They are now passed through instead of raising an error. (Pull #33)

## 2.0.0 - 2025-07-05

_This release includes a potentially breaking change and updates the compatible Python versions._

### Changed

* (**BREAKING**) Use the [IANA-registered](https://www.iana.org/assignments/media-types/application/vnd.msgpack) `application/vnd.msgpack` MIME type, instead of `application/x-msgpack` previously.
  * This impacts both the detection of msgpack-acceptable requests, as well as the MIME type used for encoding responses.
  * To continue using `application/x-msgpack` or to use any other MIME type suitable for your needs, use the new `content_type` argument on `MessagePackMiddleware`. (Pull #30)

### Removed

* Drop official support for Python 3.6, 3.7 and 3.8 which have reached EOL. (It is likely this version remains compatible in practice, but no further maintenance will be provided for these Python versions.) (Pull #29)

### Added

* Add official support for Python 3.9 through 3.13. (Pull #29)

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
