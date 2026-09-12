"""노트북에서 불러다 쓰는 EDA 헬퍼 — 결측/최빈값/유니크/dtype/정규성 요약(BasicEDA)과
IQR 이상치/샤피로 검정/상관·카이제곱 검정(AdvanceEDA)."""
import logging

import pandas as pd
import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


class BasicEDA:
    """결측률·최빈값·유니크 수·dtype·정규성을 한 표로 요약."""

    @staticmethod
    def check_nan(df: pd.DataFrame) -> pd.DataFrame:
        missing_values = df.isnull().sum()
        missing_ratio = (missing_values / len(df) * 100).round(2)
        return pd.DataFrame({
            'missing_values': missing_values,
            'missing_ratio': missing_ratio
        })

    @staticmethod
    def check_mode(df: pd.DataFrame) -> pd.DataFrame:
        modes = []
        mode_ratios = []
        for col in df.columns:
            mode_val = df[col].mode()
            if not mode_val.empty:
                mode_val_item = mode_val[0]
                mode_count = df[col][df[col] == mode_val_item].count()
                mode_ratio = (mode_count / len(df) * 100).round(2)
                modes.append(mode_val_item)
                mode_ratios.append(mode_ratio)
            else:
                modes.append(np.nan)
                mode_ratios.append(0)

        mode_df = pd.DataFrame({
            'mode_value': modes,
            'mode_ratio': mode_ratios
        }, index=df.columns)
        return mode_df

    @staticmethod
    def check_unique(df: pd.DataFrame) -> pd.DataFrame:
        unique_counts = df.nunique()
        unique_df = pd.DataFrame({
            'unique_cnt': unique_counts
        }, index=df.columns)
        return unique_df

    @staticmethod
    def check_dtype(df: pd.DataFrame) -> pd.DataFrame:
        dtypes = df.dtypes
        dtype_df = pd.DataFrame({
            'dtype': dtypes
        }, index=df.columns)
        return dtype_df

    @staticmethod
    def check_normality(df: pd.DataFrame) -> pd.DataFrame:
        numeric_cols = df.select_dtypes(include=np.number).columns
        
        if len(numeric_cols) == 0:
            print("No numeric columns to check for normality.")
            return pd.DataFrame(columns=['statistic', 'p-value'])

        normality_results = []
        for col in numeric_cols:
            data = df[col].dropna()
            if len(data) > 2:  # Shapiro-Wilk test requires at least 3 samples.
                stat, p_value = stats.shapiro(data)
                normality_results.append({'columns': col, 'statistic': f"{stat:.4f}", 'p-value': f"{p_value:.4f}"})
            else:
                normality_results.append({'columns': col, 'statistic': np.nan, 'p-value': np.nan})
        
        normality_df = pd.DataFrame(normality_results)
        if not normality_df.empty:
            normality_df = normality_df.set_index('columns')
        return normality_df

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        nan_df = self.check_nan(df)
        mode_df = self.check_mode(df)
        unique_df = self.check_unique(df)
        dtype_df = self.check_dtype(df)

        summary_df = pd.concat([dtype_df, nan_df, mode_df, unique_df], axis=1)
        summary_df.reset_index(inplace=True)
        summary_df.rename(columns={'index': 'columns'}, inplace=True)

        final_columns = ['columns', 'missing_ratio', 'mode_value', 'mode_ratio', 'unique_cnt', 'dtype']
        return summary_df[final_columns]



class AdvanceEDA:
    """IQR 이상치, 샤피로 정규성 검정, 타겟 대비 상관·카이제곱 검정."""

    @staticmethod
    def check_outlier_iqr(df: pd.DataFrame) -> pd.DataFrame:
        numeric_cols = df.select_dtypes(include=np.number).columns
        results = []

        for col in numeric_cols:
            data = df[col].dropna()
            q1 = data.quantile(0.25)
            q3 = data.quantile(0.75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr

            outliers = data[(data < lower_bound) | (data > upper_bound)]
            outlier_cnt = len(outliers)
            outlier_ratio = round(outlier_cnt / len(data) * 100, 2) if len(data) > 0 else 0

            results.append({
                'column': col,
                'q1': round(q1, 2),
                'q3': round(q3, 2),
                'iqr': round(iqr, 2),
                'lower_bound': round(lower_bound, 2),
                'upper_bound': round(upper_bound, 2),
                'outlier_cnt': outlier_cnt,
                'outlier_ratio': outlier_ratio,
                'min': round(data.min(), 2),
                'max': round(data.max(), 2)
            })
        return pd.DataFrame(results)

    @staticmethod
    def shapiro_test(df: pd.DataFrame) -> pd.DataFrame:
        """정규성 검정 (Shapiro-Wilk test)
        - p_value >= 0.05: 정규분포를 따른다고 볼 수 있음
        - p_value < 0.05: 정규분포를 따르지 않음
        - 샘플 수가 5000개 초과 시 무작위 5000개만 사용 (Shapiro 제한)
        """
        numeric_cols = df.select_dtypes(include=np.number).columns
        results = []

        for col in numeric_cols:
            data = df[col].dropna()

            if len(data) < 3:
                results.append({
                    'column': col,
                    'n_samples': len(data),
                    'statistic': np.nan,
                    'p_value': np.nan,
                    'is_normal': np.nan,
                    'skewness': np.nan,
                    'kurtosis': np.nan
                })
                continue

            # Shapiro-Wilk는 5000개 제한 — 앞에서부터 자르면 원본 정렬 순서(예: objectid 순)에
            # 따라 표본이 한쪽으로 쏠릴 수 있어 무작위로 뽑는다.
            test_data = data.sample(n=5000, random_state=42) if len(data) > 5000 else data
            stat, p_value = stats.shapiro(test_data)
            skewness = stats.skew(data)
            kurtosis = stats.kurtosis(data)

            results.append({
                'column': col,
                'n_samples': len(data),
                'statistic': round(stat, 4),
                'p_value': round(p_value, 4),
                'is_normal': p_value >= 0.05,
                'skewness': round(skewness, 4),
                'kurtosis': round(kurtosis, 4)
            })
        return pd.DataFrame(results)

    @staticmethod
    def check_correlation(df: pd.DataFrame, target: str, method: str = 'auto') -> pd.DataFrame:
        """수치형 변수와 타겟 간의 상관관계 검정

        Args:
            df: 데이터프레임
            target: 타겟 컬럼명
            method: 'auto' (정규성 기반 자동 선택), 'pearson', 'spearman'

        Returns:
            상관관계 분석 결과 DataFrame
        """
        num_cols = df.select_dtypes(include=np.number).columns
        if target in num_cols:
            num_cols = num_cols.drop(target)

        # method 결정
        if method == 'auto':
            # 정규성 검정 수행
            normality_df = AdvanceEDA.shapiro_test(df[num_cols])
            normal_ratio = normality_df['is_normal'].sum() / len(normality_df) * 100
            selected_method = 'pearson' if normal_ratio >= 50 else 'spearman'
            print(f"정규성 만족 비율: {normal_ratio:.1f}% → {selected_method.upper()} 선택")
        else:
            selected_method = method

        results = []
        for col in num_cols:
            data = df[[col, target]].dropna()

            if selected_method == 'pearson':
                corr, p_value = stats.pearsonr(data[col], data[target])
            else:
                corr, p_value = stats.spearmanr(data[col], data[target])

            results.append({
                'column': col,
                'method': selected_method,
                'correlation': round(corr, 4),
                'p_value': round(p_value, 4),
                'abs_corr': round(abs(corr), 4),
                'significant': p_value < 0.05
            })
        return pd.DataFrame(results).sort_values('abs_corr', ascending=False)

    @staticmethod
    def check_chi2_test(df: pd.DataFrame, target: str) -> pd.DataFrame:
        """모든 범주형 컬럼과 타겟 간의 카이제곱 검정 + Cramér's V"""
        cat_cols = df.select_dtypes(include='object').columns
        if 'ID' in cat_cols:
            cat_cols = cat_cols.drop('ID')

        results = []
        for col in cat_cols:
            try:
                contingency_table = pd.crosstab(df[col], df[target])
                chi2, p_value, dof, expected = stats.chi2_contingency(contingency_table)

                # 기대빈도 >= 5 비율
                expected_ratio = (expected >= 5).sum() / expected.size * 100

                # Cramér's V
                n = contingency_table.sum().sum()
                min_dim = min(contingency_table.shape) - 1
                cramers_v = np.sqrt(chi2 / (n * min_dim)) if min_dim > 0 else 0

                results.append({
                    'column': col,
                    'unique': df[col].nunique(),
                    'chi2': round(chi2, 4),
                    'p_value': round(p_value, 4),
                    'cramers_v': round(cramers_v, 4),
                    'expected_>=5_ratio': round(expected_ratio, 1),
                    'valid': expected_ratio >= 80
                })
            except ValueError as e:
                # crosstab 결과가 1차원(범주가 1개뿐)이면 chi2_contingency가
                # ValueError를 던진다 — 그 컬럼만 결과 없이 건너뛴다.
                logger.warning(f"{col} 카이제곱 검정 실패: {e}")
                results.append({
                    'column': col,
                    'unique': df[col].nunique(),
                    'chi2': np.nan,
                    'p_value': np.nan,
                    'cramers_v': np.nan,
                    'expected_>=5_ratio': np.nan,
                    'valid': False
                })
        result_df = pd.DataFrame(results)
        result_df = result_df.sort_values('p_value', ascending=True).reset_index(drop=True)
        return result_df