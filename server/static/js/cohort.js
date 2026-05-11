/**
 * Cohort-scoped API URLs (?cohort_id=) for multi-schema data routes.
 */
function getAppCohortId() {
    var fromBody = document.body && document.body.getAttribute('data-cohort-id');
    if (fromBody) return String(fromBody);
    var m = window.location.pathname.match(/\/c\/(\d+)\//);
    return m ? m[1] : '';
}

function cohortApiUrl(url) {
    if (!url || typeof url !== 'string') return url;
    if (!url.startsWith('/api/')) return url;
    if (url.indexOf('cohort_id=') !== -1) return url;
    if (url.startsWith('/api/auth/')) return url;
    // Skip cohort-prefixing for plain auth APIs only; user management is gone.
    var id = getAppCohortId();
    if (!id) return url;
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    var out = url + sep + 'cohort_id=' + encodeURIComponent(id);
    if (typeof appUrl === 'function') return appUrl(out);
    return out;
}
