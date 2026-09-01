export const SITE_NAME = '장전 브리핑';
export const SITE_TAGLINE = '지금 중요한 일을 짧게 정리합니다.';

export function isCurrentPath(href: string, pathname: string): boolean {
  const normalize = (value: string): string => {
    let decoded = value.trim() || '/';
    try {
      decoded = decodeURI(decoded);
    } catch {
      // keep the original if the path is malformed
    }
    const withLeading = decoded.startsWith('/') ? decoded : `/${decoded}`;
    if (withLeading.length > 1 && withLeading.endsWith('/')) {
      return withLeading.slice(0, -1);
    }
    return withLeading;
  };
  return normalize(href) === normalize(pathname);
}
