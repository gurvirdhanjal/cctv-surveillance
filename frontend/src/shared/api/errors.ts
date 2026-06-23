/** Typed API error hierarchy — every non-2xx response maps to one of these. */

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export class UnauthorizedError extends ApiError {
  constructor(body?: unknown) {
    super('Not authenticated', 401, body)
    this.name = 'UnauthorizedError'
  }
}

export class ForbiddenError extends ApiError {
  constructor(body?: unknown) {
    super('Insufficient permissions', 403, body)
    this.name = 'ForbiddenError'
  }
}

export class NotFoundError extends ApiError {
  constructor(body?: unknown) {
    super('Resource not found', 404, body)
    this.name = 'NotFoundError'
  }
}

export class ValidationError extends ApiError {
  constructor(body?: unknown) {
    super('Validation failed', 422, body)
    this.name = 'ValidationError'
  }
}

export class NotImplementedError extends ApiError {
  constructor(body?: unknown) {
    super('Not implemented', 501, body)
    this.name = 'NotImplementedError'
  }
}

export class ServerError extends ApiError {
  constructor(status: number, body?: unknown) {
    super('Server error', status, body)
    this.name = 'ServerError'
  }
}

/** Map any HTTP response to the correct typed error. */
export function mapHttpError(status: number, body?: unknown): ApiError {
  switch (status) {
    case 401:
      return new UnauthorizedError(body)
    case 403:
      return new ForbiddenError(body)
    case 404:
      return new NotFoundError(body)
    case 422:
      return new ValidationError(body)
    case 501:
      return new NotImplementedError(body)
    default:
      return new ServerError(status, body)
  }
}
