# %%
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.weightstats import ttest_ind
import numpy as np
from sklearn.preprocessing import PolynomialFeatures
import matplotlib.dates as mdates

# %%
data_dir = 'data'

user_active_min = pd.read_csv(f'{data_dir}/t1_user_active_min.csv')
user_variant = pd.read_csv(f'{data_dir}/t2_user_variant.csv')
user_active_min_pre = pd.read_csv(f'{data_dir}/t3_user_active_min_pre.csv')
user_attributes = pd.read_csv(f'{data_dir}/t4_user_attributes.csv')

# %%
user_active_min['dt'] = pd.to_datetime(user_active_min['dt'])
user_active_min_pre['dt'] = pd.to_datetime(user_active_min_pre['dt'])
user_variant['dt'] = pd.to_datetime(user_variant['dt'])
user_variant['signup_date'] = pd.to_datetime(user_variant['signup_date'])

# %%
# user_active_min['active_mins'].hist(bins=10)
# plt.yscale('log')
# plt.xscale('log')
# plt.show()

# %%
user_active_min_clean = user_active_min[user_active_min['active_mins'] <= 1440]  # 1440 minutes in a day
user_active_min_pre_clean = user_active_min_pre[user_active_min_pre['active_mins'] <= 1440]

# %%
# user_active_min_clean['active_mins'].hist(bins=50)
# plt.yscale('log')
# plt.xscale('log')
# plt.show()

# %%
u_act_grouped = user_active_min_clean.groupby('uid').sum()
u_act_var = user_variant.join(u_act_grouped, on='uid', how='left', lsuffix='_act', rsuffix='_var').fillna(0)

tmt_mask = u_act_var['variant_number'] == 1
y_ctl = u_act_var.loc[~tmt_mask, 'active_mins']
y_tmt = u_act_var.loc[tmt_mask, 'active_mins']

stats.ttest_ind(y_tmt, y_ctl, equal_var=False)
# %%
# y_ctl.hist(alpha=0.5)
# y_tmt.hist(alpha=0.5)
# plt.yscale('log')
# plt.xscale('log')
# plt.axvline(y_ctl.mean(), color='blue')
# plt.axvline(y_tmt.mean(), color='orange')
#
# plt.show()

# %%
y_tmt.mean() - y_ctl.mean()

# %%
user_active_min_pre_clean['dt'].describe(datetime_is_numeric=True, percentiles=[])
user_active_min_clean['dt'].describe(datetime_is_numeric=True, percentiles=[])
treat_date = user_active_min_clean['dt'].min()

# %%
act_combined = pd.concat([user_active_min_pre_clean, user_active_min_clean])

first_dates = pd.to_datetime(user_variant.loc[user_variant['uid'].isin(
    act_combined['uid']), 'signup_date'])  # act_combined.groupby('uid').min()['dt']
last_dates = act_combined.groupby('uid').max()['dt']

# %%
act_pivoted_full = (act_combined
                    .pivot(index='uid', columns='dt', values='active_mins')
                    .reindex(pd.date_range(user_active_min_pre_clean['dt'].min(),  # add days that nobody logged in on
                                           user_active_min_clean['dt'].max()),
                             axis=1,
                             fill_value=0).fillna(0))

# %%
act_pivoted = act_pivoted_full.copy()

# %%
first_dates_sq = act_pivoted.columns.values[np.newaxis, :] < first_dates.values[:, np.newaxis]
print(first_dates_sq.shape == act_pivoted.shape)
act_pivoted[first_dates_sq] = np.nan

# %%
last_dates_sq = act_pivoted.columns.values[np.newaxis, :] > last_dates.values[:, np.newaxis]
print(last_dates_sq.shape == act_pivoted.shape)
act_pivoted[last_dates_sq] = np.nan

# %%
windows = (treat_date - first_dates)
max_window = user_active_min_clean['dt'].max() - treat_date
windows[windows > max_window] = max_window

windows_sq = ((act_pivoted.columns.values[np.newaxis, :] < (treat_date - windows.values)[:, np.newaxis])
              | (act_pivoted.columns.values[np.newaxis, :] > (treat_date + windows.values)[:, np.newaxis]))
act_pivoted[windows_sq] = np.nan

# %%
pre = act_pivoted[act_pivoted.columns[act_pivoted.columns < treat_date]]
post = act_pivoted[act_pivoted.columns[act_pivoted.columns >= treat_date]]

prepost = pd.merge(pre.mean(axis=1).rename('pre'),
                   post.mean(axis=1).rename('post'),
                   on='uid')
prepost['diff'] = prepost['post'] - prepost['pre']
prepost = prepost[~prepost.isna().any(axis=1)]

treated_uids = user_variant.loc[user_variant['variant_number'] == 1, 'uid']
prepost['treated'] = False
prepost.loc[prepost.index.isin(treated_uids), 'treated'] = True

prepost = prepost.join(user_attributes, on='uid', how='left')
prepost = prepost.drop(['uid'], axis=1).join(user_variant, on='uid').drop(['uid'], axis=1)

prepost = prepost[~(prepost['signup_date'] < pd.Timestamp('2000-01-01'))]
prepost['signup_date_int'] = prepost['signup_date'].astype('int64') // 1e9 // 60 // 60 // 60 // 24
prepost['signup_date_int'] -= prepost['signup_date_int'].min()

prepost.to_csv(f'{data_dir}/combined_data.csv')

prepost_full = prepost.copy()
prepost = prepost_full.copy()

# %%
prepost = pd.read_csv(f'{data_dir}/combined_data_matched.csv').set_index('uid')

# %%
tmt = prepost_full.loc[prepost[prepost.treated & (prepost['user_type'] == 'new_user')].index]
ctl = prepost_full.loc[prepost[~prepost.treated & (prepost['user_type'] == 'new_user')].index]
tmt_pre, ctl_pre = tmt['pre'].values, ctl['pre'].values
tmt_post, ctl_post = tmt['post'].values, ctl['post'].values
pre = np.vstack([tmt_pre, ctl_pre]).mean(axis=0)

(tmt_post.mean() / tmt_pre.mean()) / (ctl_post.mean() / ctl_pre.mean())
((tmt_post - ctl_post) + pre).mean() / pre.mean()
# %%
for gender in prepost['gender'].unique():
    for user_type in prepost['user_type'].unique():
        mask = (prepost['gender'] == gender) & (prepost['user_type'] == user_type)
        treat = prepost['treated']
        ctl = prepost.loc[mask & ~treat, 'diff']
        tmt = prepost.loc[mask & treat, 'diff']
        print(gender, user_type, (tmt.mean() - ctl.mean()).round(2), stats.ttest_ind(tmt, ctl, equal_var=False)[1], sep='\t')

# %%
prepost.loc[prepost['treated'], 'diff'].hist(bins=30)
plt.yscale('log')
# plt.xscale('log')
plt.xticks([0], [0])
plt.show()

# %%
prepost.loc[prepost['treated'], 'diff'].mean() - prepost.loc[~prepost['treated'], 'diff'].mean()

# %%
prepost_gend_type_ctl = prepost[~prepost['treated']].groupby(['gender', 'user_type']).mean()
prepost_gend_type_tmt = prepost[prepost['treated']].groupby(['gender', 'user_type']).mean()

prepost_gend_ctl = prepost[~prepost['treated']].groupby('gender').mean()
prepost_gend_tmt = prepost[prepost['treated']].groupby('gender').mean()

prepost_type_ctl = prepost[~prepost['treated']].groupby('user_type').mean()
prepost_type_tmt = prepost[prepost['treated']].groupby('user_type').mean()

prepost_gend_type_tmt['diff'] - prepost_gend_type_ctl['diff']
prepost_gend_tmt['diff'] - prepost_gend_ctl['diff']
prepost_type_tmt['diff'] - prepost_type_ctl['diff']

# %%
x = pd.concat([prepost[['signup_date_int', 'variant_number', 'pre']],
               pd.get_dummies(prepost[['gender', 'user_type']])], axis=1)

y = prepost['diff']

# %%
# model = sm.OLS(y, sm.add_constant(PolynomialFeatures(degree=2).fit_transform(x))).fit()
model = sm.OLS(y, sm.add_constant(x)).fit()
model.summary()

# %%
# plt.scatter(prepost['signup_date'], prepost['diff'], c=prepost['variant_number'], s=4, alpha=0.1)
# plt.yscale('log')
# plt.show()

# %%
post_act_var = user_active_min_clean.join(user_variant, on='uid', lsuffix='_act', rsuffix='_var')
(post_act_var['signup_date'] >= post_act_var['dt_var']).any()

# %%
x = ['pre-test', 'post-test']
plt.plot(x, [prepost.loc[~prepost['treated'], 'pre'].mean(), prepost.loc[~prepost['treated'], 'post'].mean()],
         color='magenta', label='Control')

plt.plot(x, [prepost.loc[prepost['treated'], 'pre'].mean(), prepost.loc[prepost['treated'], 'post'].mean()],
         color='purple', label='Treatment')
plt.legend()
plt.show()

# %%
ind_tmt = prepost[prepost['treated']].index
ind_ctl = prepost[~prepost['treated']].index

act_timeline_tmt = act_pivoted.loc[ind_tmt]
act_timeline_ctl = act_pivoted.loc[ind_ctl]

avg_act_timeline_tmt = act_timeline_tmt.mean(axis=0)
avg_act_timeline_ctl = act_timeline_ctl.mean(axis=0)


# %%
def add_timeline_graph_metadata(title='', ylabel=''):
    plt.xticks(rotation=-45, ha="left", rotation_mode="anchor")
    plt.axvline(treat_date, color='k', ls='--', label='A/B-test began')
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xlabel('Time')
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

    plt.legend(loc='upper left')
    plt.grid(axis='y')
    plt.tight_layout()
stats.norm.rvs()

# %%

window = 15
timeline_ctl_dataviz = avg_act_timeline_ctl.rolling(window).mean()
timeline_tmt_dataviz = avg_act_timeline_tmt.rolling(window).mean()

plt.plot(timeline_ctl_dataviz.index, timeline_ctl_dataviz,
         color='magenta', label='Control')
plt.scatter(avg_act_timeline_ctl.index, avg_act_timeline_ctl,
            color='magenta', s=5, alpha=0.25)

plt.plot(timeline_tmt_dataviz.index, timeline_tmt_dataviz,
         color='purple', label='Treatment')
plt.scatter(avg_act_timeline_tmt.index, avg_act_timeline_tmt,
            color='purple', s=5, alpha=0.25)

add_timeline_graph_metadata(title=f'Average daily user activity over time in original dataset \n({window}-day rolling averages)',
                            ylabel='Average user activity (minutes/day)')
plt.show()

# %%
avg_act_timeline_diff_all = avg_act_timeline_tmt - avg_act_timeline_ctl

act_combined = pd.concat([avg_act_timeline_tmt, avg_act_timeline_ctl])
norm_factor = act_combined[act_combined.index < treat_date].mean()
avg_act_timeline_diff_all = avg_act_timeline_diff_all / norm_factor * 100  # %

timeline_all_dataviz = avg_act_timeline_diff_all.rolling(window).mean()

plt.plot(timeline_all_dataviz.index, timeline_all_dataviz,
         color='black', label='Composite', lw=2, alpha=0.7)
# plt.scatter(avg_act_timeline_diff_all.index, avg_act_timeline_diff_all,
#             color='grey', s=5, alpha=0.25)

for user_type in prepost['user_type'].unique():
    uids = prepost[prepost['user_type'] == user_type].index

    single_timeline_tmt = act_timeline_tmt[act_timeline_tmt.index.isin(uids)].mean()
    single_timeline_ctl = act_timeline_ctl[act_timeline_tmt.index.isin(uids)].mean()
    single_timeline_diff = single_timeline_tmt - single_timeline_ctl

    act_combined = pd.concat([single_timeline_tmt, single_timeline_ctl])
    norm_factor = act_combined[act_combined.index < treat_date].mean()
    single_timeline_diff = single_timeline_diff / norm_factor * 100

    timeline_single_dataviz = single_timeline_diff.rolling(window).mean()
    plt.plot(timeline_single_dataviz.index, timeline_single_dataviz, label=user_type, alpha=0.5)
    # plt.scatter(single_timeline_diff.index, single_timeline_diff, s=3, alpha=0.25)

x_annot = treat_date - pd.Timedelta('8 days')#act_combined[act_combined.index >= treat_date].index.mean()
plt.ylim(-40, 180)
h = 25
plt.annotate('Better than control', xy=(x_annot, h), size=30, color='grey', alpha=0.2,
            ha='center', va='center')
plt.annotate('Worse than control', xy=(x_annot, -h), size=30, color='grey', alpha=0.2,
            ha='center', va='center')

plt.yticks([0, 50, 100, 150])
add_timeline_graph_metadata(title=f'Average treatment effect by user type ({window}-day rolling averages)',
                            ylabel='Change in activity \ncompared to pre-test period average (%)')

plt.axhline(y=0, color='grey', ls='--')
plt.show()

# %%
for user_type in prepost['user_type'].unique():
    plt.scatter(prepost.loc[prepost['user_type'] == user_type, 'pre'], prepost.loc[prepost['user_type'] == user_type, 'diff'], s=5, alpha=0.2, label=user_type)
# plt.yscale('log')
plt.show()

# %%
tmt_pre_daily = avg_act_timeline_tmt[avg_act_timeline_tmt.index < treat_date]
ctl_pre_daily = avg_act_timeline_ctl[avg_act_timeline_ctl.index < treat_date]

plt.hist(tmt_pre_daily, bins=7, alpha=0.25, density=True, color='purple', label='Treatment')
plt.hist(ctl_pre_daily, bins=7, alpha=0.25, density=True, color='magenta', label='Control')

xx = np.linspace(min(tmt_pre_daily), max(tmt_pre_daily), len(tmt_pre_daily))
yy = stats.gaussian_kde(tmt_pre_daily.dropna())(xx)
plt.plot(xx, yy, color='purple', lw=3)

xx = np.linspace(min(ctl_pre_daily), max(ctl_pre_daily), len(ctl_pre_daily))
yy = stats.gaussian_kde(ctl_pre_daily.dropna())(xx)
plt.plot(xx, yy, color='magenta', lw=3)

plt.axvline(tmt_pre_daily.mean(), color='purple', ls='--')
plt.axvline(ctl_pre_daily.mean(), color='magenta', ls='--')

plt.title('Distribution of pre-treatment daily activity across all users\nin the original dataset')
plt.ylabel('Density')
plt.xlabel('Pre-treatment average daily activity (minutes)')
plt.legend(loc='upper center')

plt.show()
# %%

x.groupby('variant_number').mean().T
