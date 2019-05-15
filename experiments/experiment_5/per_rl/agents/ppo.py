# TODO
# * Add KL-penalized objective (loss)
# * Clipped surrogate objective
# * generalized advantage estimation  - WHEN RNN
# * finite horizon estimators
# * entropy bonus
# L2 regularization on networks. (Needed?)
# https://nervanasystems.github.io/coach/components/agents/policy_optimization/cppo.html
# https://medium.com/mlreview/making-sense-of-the-bias-variance-trade-off-in-deep-reinforcement-learning-79cf1e83d565 Variance
# https://github.com/hill-a/stable-baselines
# Much info here about stop gradient https://github.com/tensorflow/tensor2tensor/blob/master/tensor2tensor/rl/ppo.py also how to use Distributions.
# https://github.com/tensorflow/agents
# TODO
# https://github.com/Anjum48/rl-examples/blob/master/ppo/ppo_joined.py very nice implementation using dataset...
# https://medium.com/aureliantactics/ppo-hyperparameters-and-ranges-6fc2d29bccbe

# DO SOME https://github.com/ray-project/ray/blob/master/python/ray/rllib/agents/ppo/ppo.py
from scipy.signal import lfilter
import tensorflow as tf
from experiments.experiment_5.per_rl.agents.a2c import A2C
from experiments.experiment_5.per_rl.agents.agent import Agent, DecoratedAgent
from experiments.experiment_5.per_rl.agents.configuration import defaults
import numpy as np


@DecoratedAgent
class PPO(A2C):
    PARAMETERS = ["gae_lambda", "epsilon", "kl_coef"]
    DEFAULTS = defaults.PPO

    def __init__(self, **kwargs):
        super(PPO, self).__init__(**kwargs)

        self.add_operation("returns", self.generalized_advantage_estimation)

    """
    # Clip the value to reduce variability during Critic training
        # Get the predicted value
        vpred = train_model.vf
        vpredclipped = OLDVPRED + tf.clip_by_value(train_model.vf - OLDVPRED, - CLIPRANGE, CLIPRANGE)
        # Unclipped value
        vf_losses1 = tf.square(vpred - R)
        # Clipped value
        vf_losses2 = tf.square(vpredclipped - R)

        vf_loss = .5 * tf.reduce_mean(tf.maximum(vf_losses1, vf_losses2))
    """

    #def action_value_loss(self, action_value, advantage, returns, **kwargs):

    def policy_loss(self, old_logits, action, advantage, **kwargs):
        return self.clipped_surrogate_loss(old_logits, action, advantage, **kwargs)

    def clipped_surrogate_loss(self, old_logits, action, advantage, logits, **kwargs):


        neg_log_old = tf.reduce_sum(-tf.math.log(tf.clip_by_value(old_logits, 1e-7, 1)) * action, axis=1)
        neg_log_new = tf.reduce_sum(-tf.math.log(tf.clip_by_value(logits, 1e-7, 1)) * action, axis=1)

        "Conservative Policy Iteration with multiplied advantages"
        l_cpi = tf.exp(neg_log_old - neg_log_new)

        # Ratio loss with neg advantages
        pg_losses = -advantage * l_cpi

        """Clipping the l_cpi according to paper."""
        pg_losses_clipped = tf.clip_by_value(l_cpi, 1.0 - self.args["epsilon"], 1.0 + self.args["epsilon"]) * -advantage

        pg_loss = tf.reduce_mean(tf.maximum(pg_losses, pg_losses_clipped))

        # Metrics
        approxkl = .5 * tf.reduce_mean(tf.square(neg_log_new - neg_log_old))
        clipfrac = tf.reduce_mean(tf.cast(tf.greater(tf.abs(l_cpi - 1.0), self.args["epsilon"]), dtype=tf.float64))

        self.metrics.add("approxkl", approxkl, ["mean"], "train", epoch=True)
        self.metrics.add("clipfrac", clipfrac, ["mean"], "train", epoch=True)

        return pg_loss

    def discount(self, x, gamma):
        return lfilter([1], [1, -gamma], x[::-1], axis=0)[::-1]

    def generalized_advantage_estimation(self, policy, obs1, old_action_value, terminal, reward, **kwargs):
        # TODO - Use action_value or append obs1 vpred?

        action_value_new = np.concatenate((old_action_value[1:], [policy(obs1[-1:])["action_value"]]))
        action_value_old = old_action_value
        terminal_new = np.concatenate((terminal[1:], [0]))

        advantage = self.discount(
            reward +
            self.args["gamma"] * action_value_new * (1 - terminal_new) -
            action_value_old, self.args["gamma"] * self.args["gae_lambda"]
        )

        td_lambda_return = advantage + action_value_old
        advantage = (advantage - advantage.mean()) / np.maximum(advantage.std(), 1e-6)

        return dict(
            returns=np.asarray(td_lambda_return),
            advantage=np.asarray(advantage)
        )