import renderer
from agent import ManhattanAgent
from environment import Environment
from scheduler import RandomScheduler


if __name__ == "__main__":

    fps = 60
    ups = None

    rt = renderer.HTTPRenderer(fps=fps)

    env = Environment(
        height=30,
        width=50,
        depth=3,
        agents=50,
        agent_class=ManhattanAgent,
        renderer=rt,
        tile_height=32,
        tile_width=32,
        scheduler=RandomScheduler,
        ups=ups,
        ticks_per_second=1,
        spawn_interval=1,  # In seconds
        task_generate_interval=1,  # In seconds
        task_assign_interval=1  # In seconds
    )

    rt.daemon = True
    rt.start()

    env.daemon = True
    env.start()

    while True:
        for agent in env.agents:
            agent.automate()
            env.update()
            env.render()

