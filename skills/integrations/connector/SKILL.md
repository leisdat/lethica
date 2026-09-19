# Connector

## Purpose

Menyediakan abstraction untuk external service.

## Connector harus memiliki

- provider
- authentication
- configuration
- actions
- error handling
- rate-limit handling
- health check

## Rules

Business logic tidak boleh bergantung langsung pada implementation provider jika abstraction memungkinkan.
