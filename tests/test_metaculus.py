import datetime
from http import HTTPStatus
import os
import pprint
from typing import cast

from dotenv import load_dotenv
import jax.numpy as np
import pandas as pd
import pytest
import requests

import ergo
import tests.mocks
from tests.utils import random_seed

pp = pprint.PrettyPrinter(indent=4)


load_dotenv()


uname = cast(str, os.getenv("METACULUS_USERNAME"))
pwd = cast(str, os.getenv("METACULUS_PASSWORD"))
user_id_str = cast(str, os.getenv("METACULUS_USER_ID"))

if None in [uname, pwd, user_id_str]:
    raise ValueError(
        ".env is missing METACULUS_USERNAME, METACULUS_PASSWORD, or METACULUS_USER_ID"
    )

user_id = int(user_id_str)


@random_seed
def get_mock_samples(n=1000):
    return np.array(
        [
            ergo.logistic.sample_mixture(tests.mocks.mock_true_params)
            for _ in range(0, n)
        ]
    )


@random_seed
def get_mock_date_samples(date_question):
    return date_question.denormalize_samples(
        pd.Series(
            [
                ergo.logistic.sample_mixture(tests.mocks.mock_normalized_params)
                for _ in range(0, 1000)
            ]
        )
    )


class TestMetaculus:
    metaculus = ergo.Metaculus(uname, pwd)
    continuous_linear_closed_question = metaculus.get_question(3963)
    continuous_linear_open_question = metaculus.get_question(3962)
    continuous_linear_date_open_question = metaculus.get_question(4212)
    continuous_log_open_question = metaculus.get_question(3961)
    closed_question = metaculus.get_question(3965)
    binary_question = metaculus.get_question(3966)
    mock_samples = get_mock_samples()
    mock_date_samples = get_mock_date_samples(continuous_linear_date_open_question)
    mock_log_question = metaculus.make_question_from_data(
        tests.mocks.mock_log_question_data
    )

    def test_login(self):
        assert self.metaculus.user_id == user_id

    def test_get_question(self):
        """Make sure we're getting the user-specific data."""
        assert "my_predictions" in self.continuous_linear_open_question.data

    def test_question_name_default(self):
        """make sure we get the correct default name if no name is specified"""
        assert (
            self.mock_log_question.name == tests.mocks.mock_log_question_data["title"]
        )

    def test_date_normalize_denormalize(self):
        samples = self.mock_date_samples
        normalized = self.continuous_linear_date_open_question.normalize_samples(
            samples
        )
        denormalized = self.continuous_linear_date_open_question.denormalize_samples(
            normalized
        )
        assert all(denormalized == samples)

    def test_normalize_denormalize(self):
        samples = [0, 0.5, 1, 5, 10, 20]
        normalized = self.mock_log_question.normalize_samples(samples)
        denormalized = self.mock_log_question.denormalize_samples(normalized)
        assert denormalized == pytest.approx(samples, abs=1e-5)

    def test_submit_continuous_linear_open(self):
        submission = self.continuous_linear_open_question.get_submission(
            tests.mocks.mock_normalized_params
        )
        r = self.continuous_linear_open_question.submit(submission)
        assert r.status_code == HTTPStatus.ACCEPTED

    def test_submit_continuous_linear_date_open(self):
        submission = self.continuous_linear_date_open_question.get_submission(
            tests.mocks.mock_normalized_params
        )
        r = self.continuous_linear_date_open_question.submit(submission)
        assert r.status_code == HTTPStatus.ACCEPTED

    def test_submit_continuous_linear_closed(self):
        submission = self.continuous_linear_closed_question.get_submission(
            tests.mocks.mock_normalized_params
        )
        r = self.continuous_linear_closed_question.submit(submission)
        assert r.status_code == 202

    def test_submit_continuous_log_open(self):
        submission = self.continuous_log_open_question.get_submission(
            tests.mocks.mock_normalized_params
        )
        r = self.continuous_log_open_question.submit(submission)
        assert r.status_code == 202

    def test_submit_from_samples(self):
        r = self.continuous_linear_open_question.submit_from_samples(
            self.mock_samples, samples_for_fit=1000
        )
        assert r.status_code == 202

    def test_submit_binary(self):
        r = self.binary_question.submit(0.95)
        assert r.status_code == 202

    def test_submit_closed_question_fails(self):
        with pytest.raises(requests.exceptions.HTTPError):
            submission = self.closed_question.get_submission(
                tests.mocks.mock_normalized_params
            )
            self.closed_question.submit(submission)

    def test_score_binary(self):
        """smoke test"""
        self.binary_question.score_my_predictions()

    def test_get_questions(self):
        questions = self.metaculus.get_questions(question_status="closed")
        assert len(questions) >= 20

    def test_get_questions_json(self):
        questions = self.metaculus.get_questions_json(include_discussion_questions=True)
        assert len(questions) >= 20

    def test_get_questions_json_pages(self):
        two_pages = self.metaculus.get_questions_json(
            pages=2, include_discussion_questions=True
        )
        assert len(two_pages) >= 40

    def test_get_questions_player_status(self):
        qs_i_predicted = self.metaculus.make_questions_df(
            self.metaculus.get_questions_json(player_status="predicted")
        )
        assert qs_i_predicted["i_predicted"].all()

        not_predicted = self.metaculus.make_questions_df(
            self.metaculus.get_questions_json(player_status="not-predicted")
        )
        assert (not_predicted["i_predicted"] == False).all()  # noqa: E712

    def test_get_questions_question_status(self):
        open = self.metaculus.make_questions_df(
            self.metaculus.get_questions_json(question_status="open")
        )

        # the additional day is to account for difference in timezones
        assert (
            open["close_time"] > (datetime.datetime.now() - datetime.timedelta(days=1))
        ).all()

        closed = self.metaculus.make_questions_df(
            self.metaculus.get_questions_json(question_status="closed")
        )
        assert (
            closed["close_time"]
            < (datetime.datetime.now() + datetime.timedelta(days=1))
        ).all()

    @pytest.mark.xfail(reason="Fitting doesn't reliably work yet #219")
    @random_seed
    def test_submission_from_samples_linear(self):
        mixture_params = self.continuous_linear_open_question.get_submission_from_samples(
            self.mock_samples
        )
        normalized_mixture_samples = [
            ergo.logistic.sample_mixture(mixture_params) for _ in range(5000)
        ]
        mixture_samples = self.continuous_linear_open_question.denormalize_samples(
            normalized_mixture_samples
        )
        assert float(np.mean(self.mock_samples)) == pytest.approx(
            float(np.mean(mixture_samples)), rel=0.1
        )
        assert float(np.var(self.mock_samples)) == pytest.approx(
            float(np.var(mixture_samples)), rel=0.2
        )

    @pytest.mark.xfail(reason="Fitting doesn't reliably work yet #219")
    @random_seed
    def test_submitted_equals_predicted_linear(self):
        self.continuous_linear_open_question.submit_from_samples(self.mock_samples)
        self.continuous_linear_open_question.refresh_question()
        latest_prediction = (
            self.continuous_linear_open_question.get_latest_normalized_prediction()
        )
        scaled_params = self.continuous_linear_open_question.get_true_scale_mixture(
            latest_prediction
        )
        prediction_samples = np.array(
            [ergo.logistic.sample_mixture(scaled_params) for _ in range(0, 1000)]
        )
        assert float(np.mean(self.mock_samples)) == pytest.approx(
            float(np.mean(prediction_samples)), rel=0.1
        )

    @pytest.mark.xfail(reason="Fitting doesn't reliably work yet #219")
    @random_seed
    def test_submitted_equals_predicted_log(self):
        self.continuous_log_open_question.submit_from_samples(self.mock_samples)
        self.continuous_log_open_question.refresh_question()
        latest_prediction = (
            self.continuous_log_open_question.get_latest_normalized_prediction()
        )
        prediction_samples = np.array(
            [
                self.continuous_log_open_question.true_from_normalized_value(
                    ergo.logistic.sample_mixture(latest_prediction)
                )
                for _ in range(0, 5000)
            ]
        )
        assert float(np.mean(self.mock_samples)) == pytest.approx(
            float(np.mean(prediction_samples)), rel=0.1
        )

    @random_seed
    def test_get_community_prediction_linear(self):
        assert self.continuous_linear_closed_question.sample_community() > 0

    @random_seed
    def test_get_community_prediction_log(self):
        assert self.continuous_log_open_question.sample_community() > 0

    @random_seed
    def test_sample_community_binary(self):
        value = self.binary_question.sample_community()
        assert bool(value) in (True, False)


# class TestVisualPandemic:
#     metaculus = ergo.Metaculus(uname, pwd, api_domain="pandemic")
#     sf_question = metaculus.get_question(3931, name="sf_question")
#     deaths_question = metaculus.get_question(3996)
#     mock_samples = get_mock_samples(5000)

#     @random_seed
#     def test_show_prediction(self):
#         self.sf_question.show_prediction(
#             self.mock_samples, show_community=False)
#         self.sf_question.show_prediction(
#             self.mock_samples, show_community=True)

#     @random_seed
#     def test_show_prediction_log(self):
#         self.deaths_question.show_prediction(
#             self.mock_samples, show_community=False)
#         self.deaths_question.show_prediction(
#             self.mock_samples, show_community=True)

#     @random_seed
#     def test_show_community_prediction(self):
#         self.sf_question.show_community_prediction()
#         self.deaths_question.show_community_prediction()
