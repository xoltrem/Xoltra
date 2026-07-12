import jwt from 'jsonwebtoken';

const ACCESS_TTL = '10m';
const REFRESH_TTL = '30d';

export function issueTokens(userId) {
  const access = jwt.sign({ sub: userId, type: 'access' }, process.env.JWT_SECRET, { expiresIn: ACCESS_TTL });
  const refresh = jwt.sign({ sub: userId, type: 'refresh' }, process.env.JWT_REFRESH_SECRET, { expiresIn: REFRESH_TTL });
  return { access, refresh };
}

export function verifyAccess(token) {
  const payload = jwt.verify(token, process.env.JWT_SECRET);
  if (payload.type !== 'access') throw new Error('wrong_token_type');
  return payload;
}

export function verifyRefresh(token) {
  const payload = jwt.verify(token, process.env.JWT_REFRESH_SECRET);
  if (payload.type !== 'refresh') throw new Error('wrong_token_type');
  return payload;
}
