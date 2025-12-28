import matplotlib.pyplot as plt


class LiveMonitorGraphMatplotlib:
    def __init__(
        self, width=10, height=6, title="Trading Monitor", update_interval=100
    ):
        self.width = width
        self.height = height
        self.title = title
        self.update_interval = update_interval
        self.balances = []

        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(self.width, self.height))
        (self.line,) = self.ax.plot([], [], lw=2, color="blue")
        self.ax.set_title(self.title)
        self.ax.set_xlabel("Bars")
        self.ax.set_ylabel("Balance")
        self.ax.grid(True)

    def update(self, balance):
        self.balances.append(balance)
        self.line.set_data(range(len(self.balances)), self.balances)
        self.ax.relim()
        self.ax.autoscale_view()
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()
        plt.pause(self.update_interval / 1000.0)
