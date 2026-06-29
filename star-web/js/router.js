/**
 * Star (群星) SPA Router
 * Simple hash-based routing with no dependencies
 */

const routes = {};
let currentRoute = null;

/**
 * Register a route handler
 * @param {string} path - Route path (e.g. 'starmap', 'orbit')
 * @param {Function} handler - Handler function called when route is activated
 */
export function registerRoute(path, handler) {
  routes[path] = handler;
}

/**
 * Navigate to a route (updates hash and triggers handler)
 * @param {string} path - Route path
 */
export function navigate(path) {
  window.location.hash = `#${path}`;
}

/**
 * Get current route path (without hash)
 * @returns {string}
 */
export function getRoute() {
  const hash = window.location.hash.slice(1); // Remove leading '#'
  return hash || 'starmap'; // Default route
}

/**
 * Initialize router - listens to hashchange events and handles initial load
 */
export function initRouter() {
  const handleRoute = () => {
    const path = getRoute();
    if (path !== currentRoute) {
      currentRoute = path;
      const handler = routes[path];
      if (handler) {
        handler();
      } else {
        console.warn(`[Router] No handler registered for route: "${path}"`);
      }
    }
  };

  // Handle initial route on page load
  handleRoute();

  // Listen for hash changes
  window.addEventListener('hashchange', handleRoute);
}
