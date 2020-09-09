import numpy as np
from scipy.stats import gengamma
import os as os
from random import sample
from abc import ABC, abstractmethod
from YGRW.data_interp import JumpDistFromAngle

CUR_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(CUR_DIR, "data")

deg = np.pi / 180


class Stepper(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def generate_step(self, *args, **kwargs):
        raise NotImplementedError

    def generate_bound_step(self, *args, **kwargs):
        """
        If a child class does not have this method defined,
        call child class' generate step method.
        """
        return self.generate_step(*args, **kwargs)


class AngleStepper(ABC):
    """
    Generates an angle for a successive step defined with respect to the previous
    step along [-180, 180] where clockwise is positive and counterclockwise is
    negative. In other words, an angle of 0 would correspond to no change in angle,
    +- 90 degrees correspond to right and left respectively, and -180 and 180 are
    both antiparallel to the previous angle.
    """

    def __init__(self):
        pass

    @abstractmethod
    def generate_angle(self, *args, **kwargs):
        raise NotImplementedError


class UniformSteps(Stepper):
    def __init__(self, lower: float = -1, upper: float = 1):

        self.lower = lower
        self.upper = upper
        super().__init__()

    def generate_step(self, prev_step=None, prev_angle=None):
        return np.random.uniform(self.lower, self.upper, size=2)


class GaussianSteps(Stepper):
    def __init__(self, mu: float = 0, sig: float = 1):

        self.mu = mu
        self.sig = sig
        super().__init__()

    def generate_step(self, prev_step=None, prev_angle=None):
        return np.random.normal(loc=self.mu, scale=self.sig, size=2)

    def generate_bound_step(self, prev_step=None, prev_angle=None):
        return np.random.normal(loc=self.mu, scale=self.sig / 2, size=2)


class GammaSteps(Stepper):
    def __init__(
        self,
        shape: float = 0,
        rate: float = 1,
        bound_shape: float = None,
        bound_rate: float = None,
    ):
        self.shape = shape
        self.rate = rate

        self.bound_shape = bound_shape or shape
        self.bound_rate = bound_rate or rate

        super().__init__()

    def generate_step(self, prev_step=None, prev_angle=None):

        # TODO incorporate anglestepper
        magnitude = gengamma.rvs(self.shape, self.rate, 1)
        angle = np.random.uniform(low=-180, high=180, size=1)

        x_step = np.cos(angle * deg) * magnitude
        y_step = np.sin(angle * deg) * magnitude

        return np.array((x_step, y_step))

    def generate_bound_step(self, prev_step=None, prev_angle=None):
        return gengamma.rvs(self.bound_shape, self.bound_rate, 2)


class UniformAngle(AngleStepper):
    def __init__(self):
        super().__init__()

    @staticmethod
    def generate_angle():
        return np.random.uniform(low=-180, high=180, size=1)


class ExperimentalAngle(AngleStepper):
    """
    Draws from experimental observation of the distribution of angles
    in successive steps.
    """

    def __init__(self, data_path: str = None):
        data_path = data_path or os.path.join(DATA_DIR, "angle_correlation.csv")
        data = np.loadtxt(data_path, skiprows=1, delimiter=",", usecols=range(1, 3))
        self.x = data[:, 0]
        self.y = data[:, 1]
        self.y /= np.sum(self.y)
        super().__init__()

    def generate_angle(self):

        angle = np.random.choice(self.x, size=1, p=self.y)
        sign = sample([-1, 1], k=1)
        return angle * sign


class ExperimentalSteps(Stepper, UniformAngle):
    def __init__(self, data_path: str = None):

        data_path = data_path or os.path.join(DATA_DIR, "jump_distances_isotropic.csv")
        data = np.loadtxt(data_path, skiprows=1, usecols=[1, 2], delimiter=",")
        self.x = data[:, 0]
        self.y = data[:, 1]
        super(Stepper).__init__()
        super(UniformAngle).__init__()

    def generate_step(self, prev_step=None, prev_angle=None):
        """
        Generate a uniform random angle and magnitude.
        """

        angle = self.generate_angle()
        magnitude = np.random.choice(self.x, size=1, p=self.y)

        x_step = np.cos(angle * deg) * magnitude
        y_step = np.sin(angle * deg) * magnitude

        return np.array((x_step, y_step))


class GammaAngleSteps(GammaSteps):
    """
    Draws from experimental observation of the distribution of angles,
    and the distribution of magnitudes in those angles.
    """

    def __init__(
        self,
        shape: float = 0,
        rate: float = 1,
        bound_shape: float = None,
        bound_rate: float = None,
    ):

        self.astepper = ExperimentalAngle()

        super().__init__(
            shape=shape, rate=rate, bound_shape=bound_shape, bound_rate=bound_rate
        )

    def generate_step(self, prev_step: np.ndarray = None, prev_angle: float = 0):

        angle = self.astepper.generate_angle()
        new_theta = prev_angle + angle

        magnitude = gengamma.rvs(self.shape, self.rate, 1)

        x_step = np.cos(new_theta) * magnitude
        y_step = np.sin(new_theta) * magnitude
        return np.array([x_step, y_step]).reshape(2)

    def generate_bound_step(self, prev_step, prev_angle):

        angle = self.astepper.generate_angle()
        new_theta = prev_angle + angle

        angle_mag = abs(angle)
        magnitude = gengamma.rvs(self.bound_shape, self.bound_rate, 1)

        x_step = np.cos(new_theta) * magnitude
        y_step = np.sin(new_theta) * magnitude
        return np.array([x_step, y_step]).reshape(2)


class ExperimentalAngleSteps(Stepper):
    """
    Draws from experimental observation of the distribution of angles,
    and the distribution of magnitudes in those angles.
    """

    def __init__(self):

        self.jdfa = JumpDistFromAngle()

        self.astepper = ExperimentalAngle()

        super().__init__()

    def generate_step(self, prev_step: np.ndarray, prev_angle: float):

        angle = self.astepper.generate_angle()
        new_theta = prev_angle + angle

        angle_mag = abs(angle)
        jump_distribution = self.jdfa.distribution_from_angle(angle_mag)
        jump_size = np.random.choice(self.jdfa.jump_values, size=1, p=jump_distribution)

        x_step = np.cos(new_theta) * jump_size
        y_step = np.sin(new_theta) * jump_size
        return np.array([x_step, y_step]).reshape(2)

    def generate_bound_step(self, prev_step, prev_angle):

        return self.generate_step(prev_step, prev_angle) / 10