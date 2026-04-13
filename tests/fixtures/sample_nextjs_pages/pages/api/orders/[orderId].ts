import type { NextApiRequest, NextApiResponse } from 'next';

type OrderPayload = {
  note: string;
  urgent?: boolean;
};

interface Order {
  id: string;
  status: string;
  note?: string;
}

/**
 * Read or update a single order.
 */
export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  switch (req.method) {
    case 'GET': {
      const { includeHistory } = req.query;
      const order: Order = {
        id: String(req.query.orderId),
        status: includeHistory ? 'historical' : 'queued',
      };
      return res.status(200).json(order);
    }
    case 'PATCH': {
      const payload: OrderPayload = req.body;
      return res.status(200).json({
        id: String(req.query.orderId),
        status: 'updated',
        note: payload.note,
      });
    }
    default:
      return res.status(405).json({ error: 'Method not allowed' });
  }
}
