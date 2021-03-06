import subprocess
import sys
from builtins import ImportError
import os

from deep_logistics.agent import Agent

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"   # see issue #152
os.environ["CUDA_VISIBLE_DEVICES"] = "5,6,7,8,9,10,11,12"


def install(package):
    subprocess.call([sys.executable, "-m", "pip", "install", "--user", package])


try:
    import gym
    import ray
    from gym import Space
    from ray.rllib import MultiAgentEnv
    import os
    import numpy as np
    from ray import tune
    from ray.rllib.agents import ppo
    from ray.rllib.agents.ppo.ppo_policy_graph import PPOPolicyGraph
    from ray.tune import register_env, grid_search, run_experiments
    from deep_logistics import DeepLogistics
    from deep_logistics import SpawnStrategies
    from gym.spaces import Tuple, Discrete, Box

    from experiments.experiment_2.rllib_ppo.reward_functions import Reward0
    from experiments.experiment_2.rllib_ppo.state_representations import State0
except ImportError as e:
    print(e)
    install("gym")
    install("lz4")
    install("SharedArray")
    install("pygame")
    install("ray[rllib]")
    install("setproctitle")
    install("opencv-python")
    install("numpy")
    install("tensorflow-gpu")
    install("tensorflow")
    install("psutil")
    exit(0)


class DeepLogisticsMultiEnv(MultiAgentEnv):

    def __init__(self, state, reward, width, height, depth, taxi_n, group_type="individual", graphics_render=False, delivery_locations=None):
        os.environ["MKL_NUM_THREADS"] = "1"
        self.env = DeepLogistics(width=width,
                                 height=height,
                                 depth=depth,
                                 taxi_n=taxi_n,
                                 taxi_agent=Agent,
                                 ups=None,
                                 graphics_render=graphics_render,
                                 #delivery_locations=delivery_locations,
                                 #spawn_strategy=SpawnStrategies.RandomSpawnStrategy
                                 )
        self.state_representation = state(self.env)
        self.reward_function = reward
        self._render = graphics_render

        self.observation_space = Box(low=-1, high=1, shape=self.state_representation.generate(self.env.agents[0]).shape, dtype=np.float32)
        self.action_space = Discrete(self.env.action_space.N_ACTIONS)

        self.agents = {"agent_%s" % i: self.env.agents[i] for i in range(taxi_n)}

        self.total_steps = 0

        """Set up grouping for the environments."""
        if group_type == "individual":
            self.grouping = {
                "group_%s" % x: ["agent_%s" % x] for x in range(taxi_n)
            }
        elif group_type == "grouped":
            self.grouping = {
                'group_1': ["agent_%s" % x for x in range(taxi_n)]
            }
        else:
            raise NotImplementedError("The group type %s is not implemented." % group_type)

        self.with_agent_groups(
                groups=self.grouping,
                obs_space=Tuple([self.observation_space for _ in range(taxi_n)]),
                act_space=Tuple([self.action_space for _ in range(taxi_n)])
            )

    def step(self, action_dict):
        self.total_steps += 1

        # TODO this loop does not make sense when using multiple policies. Now we do 1 action for all taxis with a single policy (i think) instead of 1 action per policy
        # Cluster: https://ray.readthedocs.io/en/latest/install-on-docker.html#launch-ray-in-docker<
        info_dict = {}
        reward_dict = {}
        terminal_dict = {"__all__": False}
        state_dict = {}

        """Perform actions in environment."""
        for agent_name, action in action_dict.items():
            self.agents[agent_name].do_action(action=action)

        """Update the environment"""
        self.env.update()
        if self._render:
            self.env.render()

        """Evaluate score"""
        t__all__ = False
        for agent_name, agent in action_dict.items():
            reward, terminal = self.reward_function(self.agents[agent_name])

            reward_dict[agent_name] = reward
            terminal_dict[agent_name] = terminal

            if terminal:
                t__all__ = terminal

            state_dict[agent_name] = self.state_representation.generate(self.agents[agent_name])

        """Update terminal dict"""
        terminal_dict["__all__"] = t__all__

        return state_dict, reward_dict, terminal_dict, info_dict

    def reset(self):
        self.env.reset()

        self.total_steps = 0

        return {
            agent_name: self.state_representation.generate(agent) for agent_name, agent in self.agents.items()
        }

    @staticmethod
    def on_episode_end(info):
        episode = info["episode"]
        env = info["env"].envs[0]

        deliveries = 0
        pickups = 0
        for agent in env.env.agents:
            deliveries += agent.total_deliveries
            pickups += agent.total_pickups

        deliveries = deliveries / len(env.env.agents)
        pickups = pickups / len(env.env.agents)

        episode.custom_metrics["deliveries"] = deliveries
        episode.custom_metrics["pickups"] = pickups


if __name__ == "__main__":
    ray.init(num_gpus=len(os.environ["CUDA_VISIBLE_DEVICES"].split(",")), num_cpus=os.cpu_count()-1)

    class DeepLogisticsMultiEnv1(DeepLogisticsMultiEnv):

        def __init__(self):
            DeepLogisticsMultiEnv.__init__(self, **dict(
                state=State0,
                reward=Reward0,
                width=5,
                height=5,
                depth=3,
                taxi_n=2,
                group_type="individual",
                graphics_render=False,
                delivery_locations=[
                    (2, 2), (2, 7),
                    (7, 2), (7, 7)
                ]

            ))

    env = DeepLogisticsMultiEnv1()

    register_env("DeepLogisticsMultiEnv1", lambda config: DeepLogisticsMultiEnv1())

    policy_graphs = {
        k: (PPOPolicyGraph, env.observation_space, env.action_space, dict(
            gamma=0.95
        )) for k, a in env.agents.items()
    }
    policy_ids = list(policy_graphs.keys())

    trainer = ppo.PPOAgent(env="DeepLogisticsMultiEnv1",
                           config=dict(
                               multiagent=dict(
                                   policy_graphs=policy_graphs,
                                   policy_mapping_fn=lambda agent_id: agent_id
                               ),
                               callbacks=dict(
                                   on_episode_end=tune.function(DeepLogisticsMultiEnv.on_episode_end)
                               )
                               
                               #num_envs_per_worker=4,
                               #num_workers=2
                           ))
    while True:
        print(":D")
        print(trainer.train())
1
