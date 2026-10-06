export default {
  async test(ctrl, env, ctx) {
    const resp = await env.PYTHON.fetch('http://example.com/websocket', {
      headers: { Upgrade: 'websocket' },
    });
    const ws = resp.webSocket;
    if (!ws) {
      throw new Error('No websocket');
    }
    ws.accept();
    const messagePromise = new Promise((resolve) => {
      ws.addEventListener('message', (msg) => {
        resolve(msg.data);
      });
    });
    ws.send('test');

    const message = await messagePromise;
    if (message !== 'hello') {
      throw new Error(`Unexpected websocket message: ${message}`);
    }
    ws.close();
  },
};
