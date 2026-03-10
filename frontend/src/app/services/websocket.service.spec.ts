/**
 * WebSocket Service Tests
 */

import { TestBed, fakeAsync, tick, discardPeriodicTasks } from '@angular/core/testing';
import { WebSocketService, ConnectionState } from './websocket.service';

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = [];

  url: string;
  readyState = WebSocket.CONNECTING;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  sentMessages: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sentMessages.push(data);
  }

  close(): void {
    this.readyState = WebSocket.CLOSED;
  }

  // Test helpers
  simulateOpen(): void {
    this.readyState = WebSocket.OPEN;
    if (this.onopen) {
      this.onopen(new Event('open'));
    }
  }

  simulateMessage(data: any): void {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }));
    }
  }

  simulateClose(): void {
    this.readyState = WebSocket.CLOSED;
    if (this.onclose) {
      this.onclose(new CloseEvent('close'));
    }
  }

  simulateError(): void {
    if (this.onerror) {
      this.onerror(new Event('error'));
    }
  }
}

describe('WebSocketService', () => {
  let service: WebSocketService;
  let originalWebSocket: typeof WebSocket;

  beforeEach(() => {
    MockWebSocket.instances = [];
    originalWebSocket = (globalThis as any).WebSocket;
    (globalThis as any).WebSocket = MockWebSocket as any;

    TestBed.configureTestingModule({});
    service = TestBed.inject(WebSocketService);
  });

  afterEach(() => {
    service.disconnect();
    (globalThis as any).WebSocket = originalWebSocket;
  });

  function getLatestMock(): MockWebSocket {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1];
  }

  describe('connect', () => {
    it('should create a WebSocket connection', () => {
      service.connect('test-session').subscribe();
      expect(MockWebSocket.instances.length).toBe(1);
      expect(getLatestMock().url).toContain('/ws/test-session');
    });

    it('should emit true and set state to connected on open', (done) => {
      service.connect('test-session').subscribe({
        next: (connected) => {
          expect(connected).toBe(true);
          expect(service.isConnected).toBe(true);
          done();
        }
      });

      getLatestMock().simulateOpen();
    });

    it('should update connection state observable', (done) => {
      const states: ConnectionState[] = [];
      service.connectionState$.subscribe(state => states.push(state));

      service.connect('test-session').subscribe({
        next: () => {
          // Initial 'disconnected' + 'connected'
          expect(states).toContain('connected');
          done();
        }
      });

      getLatestMock().simulateOpen();
    });

    it('should emit error on WebSocket error', (done) => {
      service.connect('test-session').subscribe({
        error: () => {
          done();
        }
      });

      getLatestMock().simulateError();
    });
  });

  describe('disconnect', () => {
    it('should close the WebSocket', () => {
      service.connect('test-session').subscribe();
      getLatestMock().simulateOpen();

      service.disconnect();
      expect(service.isConnected).toBe(false);
    });

    it('should set state to disconnected', (done) => {
      service.connect('test-session').subscribe({
        next: () => {
          service.disconnect();

          service.connectionState$.subscribe(state => {
            expect(state).toBe('disconnected');
            done();
          });
        }
      });

      getLatestMock().simulateOpen();
    });

    it('should not reconnect after intentional disconnect', fakeAsync(() => {
      service.connect('test-session').subscribe();
      getLatestMock().simulateOpen();

      const countBefore = MockWebSocket.instances.length;
      service.disconnect();

      tick(5000);
      expect(MockWebSocket.instances.length).toBe(countBefore);

      discardPeriodicTasks();
    }));
  });

  describe('sendMessage', () => {
    it('should send a JSON message when connected', () => {
      service.connect('test-session').subscribe();
      getLatestMock().simulateOpen();

      service.sendMessage('Hello');
      const sent = JSON.parse(getLatestMock().sentMessages[0]);
      expect(sent.type).toBe('message');
      expect(sent.content).toBe('Hello');
    });

    it('should not send when disconnected', () => {
      service.sendMessage('Hello');
      // No socket created, so no error thrown - just logs
      expect(MockWebSocket.instances.length).toBe(0);
    });
  });

  describe('messages', () => {
    it('should emit parsed WebSocket messages', (done) => {
      service.messages$.subscribe(msg => {
        expect(msg.type).toBe('response');
        expect(msg.data).toBe('test-data');
        done();
      });

      service.connect('test-session').subscribe();
      getLatestMock().simulateOpen();
      getLatestMock().simulateMessage({ type: 'response', data: 'test-data' });
    });
  });

  describe('reconnect', () => {
    it('should attempt reconnect after unexpected close', fakeAsync(() => {
      service.connect('test-session').subscribe();
      const mock = getLatestMock();
      mock.simulateOpen();

      const countBefore = MockWebSocket.instances.length;

      // Simulate unexpected close
      mock.simulateClose();

      // After 1s backoff, should attempt reconnect
      tick(1000);
      expect(MockWebSocket.instances.length).toBe(countBefore + 1);

      // Clean up
      service.disconnect();
      discardPeriodicTasks();
    }));

    it('should use exponential backoff', fakeAsync(() => {
      service.connect('test-session').subscribe();
      getLatestMock().simulateOpen();

      // First disconnect - 1s backoff
      getLatestMock().simulateClose();
      tick(1000);
      const afterFirst = MockWebSocket.instances.length;

      // Second disconnect - 2s backoff
      getLatestMock().simulateClose();
      tick(1000);
      expect(MockWebSocket.instances.length).toBe(afterFirst); // Not yet
      tick(1000);
      expect(MockWebSocket.instances.length).toBe(afterFirst + 1); // Now

      service.disconnect();
      discardPeriodicTasks();
    }));

    it('should set state to reconnecting during reconnect', fakeAsync(() => {
      const states: ConnectionState[] = [];
      service.connectionState$.subscribe(state => states.push(state));

      service.connect('test-session').subscribe();
      getLatestMock().simulateOpen();

      getLatestMock().simulateClose();

      expect(states).toContain('reconnecting');

      service.disconnect();
      discardPeriodicTasks();
    }));

    it('should stop reconnecting after max attempts', fakeAsync(() => {
      service.connect('test-session').subscribe();
      getLatestMock().simulateOpen();

      // Simulate 10 failed reconnect cycles
      for (let i = 0; i < 11; i++) {
        getLatestMock().simulateClose();
        tick(30000); // Max backoff
      }

      const finalCount = MockWebSocket.instances.length;

      // Should not create more connections
      tick(60000);
      expect(MockWebSocket.instances.length).toBe(finalCount);

      service.disconnect();
      discardPeriodicTasks();
    }));
  });

  describe('heartbeat', () => {
    it('should send ping after 30 seconds', fakeAsync(() => {
      service.connect('test-session').subscribe();
      getLatestMock().simulateOpen();

      tick(30000);

      const pings = getLatestMock().sentMessages.filter(
        m => JSON.parse(m).type === 'ping'
      );
      expect(pings.length).toBe(1);

      service.disconnect();
      discardPeriodicTasks();
    }));

    it('should stop heartbeat on disconnect', fakeAsync(() => {
      service.connect('test-session').subscribe();
      const mock = getLatestMock();
      mock.simulateOpen();

      service.disconnect();

      tick(60000);
      // After disconnect, no new pings should be sent
      const pings = mock.sentMessages.filter(
        m => JSON.parse(m).type === 'ping'
      );
      expect(pings.length).toBe(0);

      discardPeriodicTasks();
    }));
  });

  describe('cancel', () => {
    it('should send cancel message', () => {
      service.connect('test-session').subscribe();
      getLatestMock().simulateOpen();

      service.cancel();
      const sent = JSON.parse(getLatestMock().sentMessages[0]);
      expect(sent.type).toBe('cancel');
    });
  });
});
