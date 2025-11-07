class BinanceWebSocketApiManager:
    def __init__(self, *args, **kwargs):
        self._buffer = []
        self._stopping = False

    def create_stream(self, *_args, **_kwargs):
        return "stream-id"

    def is_manager_stopping(self):
        return self._stopping

    def pop_stream_data_from_stream_buffer(self):
        try:
            return self._buffer.pop(0)
        except IndexError:
            return None

    def stop_manager_with_all_streams(self):
        self._stopping = True

