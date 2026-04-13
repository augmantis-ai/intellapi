// Sample Express application for testing

const express = require('express');
const app = express();

app.use(express.json());

// ─── Auth middleware (simulated) ────────────────────────────────────────

const authMiddleware = (req, res, next) => {
  const token = req.headers.authorization;
  if (!token) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  req.user = { id: 1, name: 'Test User' };
  next();
};

// ─── Users routes ──────────────────────────────────────────────────────

/**
 * List all users with pagination
 * @query {number} skip - Number of records to skip
 * @query {number} limit - Max records to return
 */
app.get('/api/users', (req, res) => {
  const { skip = 0, limit = 10 } = req.query;
  res.json([]);
});

/**
 * Get a specific user by ID
 * @param {number} id - User ID
 */
app.get('/api/users/:id', (req, res) => {
  res.json({ id: req.params.id, name: 'John', email: 'john@example.com' });
});

/**
 * Create a new user
 * @body {string} name - User's full name
 * @body {string} email - User's email address
 * @body {number} [age] - User's age
 */
app.post('/api/users', (req, res) => {
  const { name, email, age } = req.body;
  res.status(201).json({ id: 1, name, email, age });
});

/**
 * Update an existing user
 */
app.put('/api/users/:id', (req, res) => {
  res.json({ id: req.params.id, ...req.body });
});

/**
 * Delete a user. Requires authentication.
 */
app.delete('/api/users/:id', authMiddleware, (req, res) => {
  res.status(204).send();
});

// ─── Items routes ──────────────────────────────────────────────────────

const itemRouter = express.Router();

/**
 * List all items
 * @query {number} [owner_id] - Filter by owner ID
 */
itemRouter.get('/', (req, res) => {
  res.json([]);
});

/**
 * Create a new item. Requires authentication.
 */
itemRouter.post('/', authMiddleware, (req, res) => {
  res.status(201).json({ id: 1, ...req.body });
});

app.use('/api/items', itemRouter);

// ─── Health check ──────────────────────────────────────────────────────

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

module.exports = app;
