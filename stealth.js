// Pass the User-Agent test
Object.defineProperty(navigator, 'userAgent', {
    get: () => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
});

// Pass the webdriver test
Object.defineProperty(navigator, 'webdriver', {
    get: () => false,
});

// Pass the Chrome test
window.chrome = {
    runtime: {},
    // etc.
};

// Pass the permissions test
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
    Promise.resolve({ state: Notification.permission }) :
    originalQuery(parameters)
);

// Pass the plugins test
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Pass the languages test
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});