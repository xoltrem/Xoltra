import { withAuth } from '../../../lib/withAuth';
import { getMemoryForUser } from '../../../lib/memoryEngine';

export default withAuth(async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).end();
  const memory = await getMemoryForUser(req.userId, req.query.query || '');
  res.status(200).json({ memory });
});
