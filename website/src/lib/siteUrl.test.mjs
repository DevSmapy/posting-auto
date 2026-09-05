import assert from 'node:assert/strict';
import { test } from 'node:test';
import { resolveSiteUrl } from './siteUrl.mjs';

test('uses SITE_BASE_URL when set', () => {
  assert.equal(
    resolveSiteUrl({ SITE_BASE_URL: 'https://briefing.example/' }, ['build']),
    'https://briefing.example',
  );
});

test('uses Vercel production host when SITE_BASE_URL is empty', () => {
  assert.equal(
    resolveSiteUrl(
      { VERCEL_PROJECT_PRODUCTION_URL: 'jangjeon-briefing.vercel.app' },
      ['build'],
    ),
    'https://jangjeon-briefing.vercel.app',
  );
});

test('uses VERCEL_URL when production host is absent', () => {
  assert.equal(
    resolveSiteUrl({ VERCEL_URL: 'https://jangjeon-briefing-abc.vercel.app' }, ['build']),
    'https://jangjeon-briefing-abc.vercel.app',
  );
});

test('throws on build without a resolvable origin', () => {
  assert.throws(() => resolveSiteUrl({}, ['build']), /SITE_BASE_URL is required/);
});

test('falls back for non-build commands', () => {
  assert.equal(resolveSiteUrl({}, ['dev']), 'https://briefing.example');
});
