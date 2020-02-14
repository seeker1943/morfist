import numpy as np
import scipy.stats
import copy


class MixedSplitter:
    def __init__(self,
                 x,
                 y,
                 max_features='sqrt',
                 min_samples_leaf=5,
                 choose_split='mean',
                 class_targets=None):
        self.n_train = x.shape[0]
        self.n_features = x.shape[1]
        self.n_targets = y.shape[1]
        self.class_targets = class_targets if class_targets else []
        self.max_features = max_features
        self.min_samples_leaf = min_samples_leaf
        self.root_impurity = self.__impurity_node(y)
        self.choose_split = choose_split

    def split(self, x, y):
        # Maximum number of features to try for the best split
        # Not all of them are tried because this is a Random Tree
        if self.max_features == 'sqrt':
            self.max_features = int(np.ceil(np.sqrt(self.n_features)))

        return self.__find_best_split(x, y)

    def __find_best_split(self, x, y):
        if x.shape[0] <= self.min_samples_leaf:
            return None, None, np.inf

        # Best feature
        best_f = None
        # Best value
        best_v = None
        # Best impurity
        best_imp = -np.inf

        # Random selection of the features to try for the best split
        try_features = np.random.choice(
            np.arange(self.n_features),
            self.max_features,
            replace=False
        )

        # Try each of the selected features and find which of them gives the best split(higher impurity)
        for f in try_features:
            values = np.unique(x[:, f])
            # We ensure that the value appears at least 1 times (FIXME??)
            if values.size < 2:
                continue
            # TODO: what's going on here
            values = (values[:-1] + values[1:]) / 2

            # random value sub-sampling
            values = np.random.choice(values, min(2, values.size))
            # Try to split with this specific combination of feature, value and impurity
            # If it's better than the previous one, save the values
            for v in values:
                imp = self.__try_split(x, y, f, v)
                if imp > best_imp:
                    best_f, best_v, best_imp = f, v, imp

        return best_f, best_v, best_imp

    # Try a specific split
    # Parameters
    #   x: x data
    #   y: y data
    #   f: feature
    #   t: value
    def __try_split(self, x, y, f, t):
        left_idx = x[:, f] <= t
        right_idx = x[:, f] > t

        return self.__impurity_split(y, y[left_idx, :], y[right_idx, :])

    # Calculate the impurity of a node
    def __impurity_node(self, y):
        # Calculate the impurity value for the classification task
        def impurity_class(y_class):
            # FIXME: this is one of the bottlenecks
            y_class = y_class.astype(int)
            freq = np.bincount(y_class) / y_class.size
            freq = freq[freq != 0]
            return 0 - np.array([f * np.log2(f) for f in freq]).sum()

        # Calculate the impurity value for the regression task
        def impurity_reg(y_reg):
            if np.unique(y_reg).size < 2:
                return 0

            n_bins = 100
            # FIXME: this is one the bottlenecks
            freq, _ = np.histogram(y, bins=n_bins, density=True)
            proba = (freq + 1) / (freq.sum() + n_bins)
            bin_width = (y_reg.max() - y_reg.min()) / n_bins

            return 0 - bin_width * (proba * np.log2(proba)).sum()

        # TODO: what is this delta?
        delta = 0.0001
        imp = np.zeros(self.n_targets)
        # Calculate the impurity value for each of the targets(classification or regression)
        for i in range(self.n_targets):
            if i in self.class_targets:
                imp[i] = impurity_class(y[:, i]) + delta
            else:
                imp[i] = impurity_reg(y[:, i]) + delta
        return imp

    # Calculate the impurity of a split
    def __impurity_split(self, y, y_left, y_right):
        n_parent = y.shape[0]
        n_left = y_left.shape[0]
        n_right = y_right.shape[0]

        if n_left < self.min_samples_leaf or n_right < self.min_samples_leaf:
            return np.inf
        else:
            imp_left = self.__impurity_node(y_left) / self.root_impurity
            imp_right = self.__impurity_node(y_right) / self.root_impurity
            imp_parent = self.__impurity_node(y) / self.root_impurity

            gain_left = (n_left / n_parent) * (imp_parent - imp_left)
            gain_right = (n_right / n_parent) * (imp_parent - imp_right)
            gain = gain_left + gain_right

            if self.choose_split == 'mean':
                return gain.mean()
            else:
                return gain.max()


# Build a Random Tree
# Parameters:
#   max_features:
#   min_samples_leaf: minimum amount of samples in each leaf
#   choose_split: method used to find the best split
#   class_targets: features that are part of the classification task
class MixedRandomTree:
    def __init__(self,
                 max_features='sqrt',
                 min_samples_leaf=5,
                 choose_split='mean',
                 class_targets=None):
        self.min_samples_leaf = min_samples_leaf
        self.max_features = max_features
        self.class_targets = class_targets if class_targets else []
        self.choose_split = choose_split
        self.n_targets = 0
        self.f = []
        self.t = []
        self.v = []
        self.l = []
        self.r = []
        self.n = []

    def fit(self, x, y):
        if y.ndim == 1:
            y = y.reshape((y.size, 1))

        self.n_targets = y.shape[1]

        splitter = MixedSplitter(x,
                                 y,
                                 self.max_features,
                                 self.min_samples_leaf,
                                 self.choose_split,
                                 self.class_targets)

        split_f = []
        split_t = []
        leaf_value = []
        left_child = []
        right_child = []
        n_i = []

        split_queue = [(x, y)]
        i = 0
        # Build the tree until all values are covered
        while len(split_queue) > 0:
            next_x, next_y = split_queue.pop(0)

            leaf_value.append(self._make_leaf(next_y))
            n_i.append(next_y.shape[0])

            f, t, imp = splitter.split(next_x, next_y)

            split_f.append(f)
            split_t.append(t)
            if f:
                left_child.append(i + len(split_queue) + 1)
                right_child.append(i + len(split_queue) + 2)
            else:
                left_child.append(None)
                right_child.append(None)

            if f:
                l_idx = next_x[:, f] <= t
                r_idx = next_x[:, f] > t

                split_queue.append((next_x[l_idx, :], next_y[l_idx, :]))
                split_queue.append((next_x[r_idx, :], next_y[r_idx, :]))

            i += 1

        self.f = np.array(split_f)
        self.t = np.array(split_t)
        self.v = np.array(leaf_value)
        self.l = np.array(left_child)
        self.r = np.array(right_child)
        self.n = np.array(n_i)

    def _make_leaf(self, y):
        y_ = np.zeros(self.n_targets)
        for i in range(self.n_targets):
            if i in self.class_targets:
                y_[i] = np.argmax(np.bincount(y[:, i].astype(int)))
            else:
                y_[i] = y[:, i].mean()
        return y_

    def predict(self, x):
        n_test = x.shape[0]
        pred = np.zeros((n_test, self.n_targets))

        def traverse(x_traverse, test_idx, node_idx):
            if test_idx.size < 1:
                return

            if not self.f[node_idx]:
                pred[test_idx, :] = self.v[node_idx]
            else:
                l_idx = x_traverse[:, self.f[node_idx]] <= self.t[node_idx]
                r_idx = x_traverse[:, self.f[node_idx]] > self.t[node_idx]

                traverse(x_traverse[l_idx, :], test_idx[l_idx], self.l[node_idx])
                traverse(x_traverse[r_idx, :], test_idx[r_idx], self.r[node_idx])

        traverse(x, np.arange(n_test), 0)
        return pred

    def print(self):
        def print_l(level, i):
            if self.f[i]:
                print('\t' * level + '[{} <= {}]:'.format(self.f[i], self.t[i]))
                print_l(level + 1, self.l[i])
                print_l(level + 1, self.r[i])
            else:
                print('\t' * level + str(self.v[i]) + ' ({})'.format(self.n[i]))

        print_l(0, 0)


# Build the Random Forest model
# Parameters:
#   n_estimators: number of trees in the forest
#   max_features:
#   min_samples_leaf: minimum amount of samples in each leaf
#   choose_split: method used to find the best split
#   class_targets: features that are part of the classification task
class MixedRandomForest:
    def __init__(self,
                 n_estimators=10,
                 max_features='sqrt',
                 min_samples_leaf=5,
                 choose_split='mean',
                 class_targets=None):
        self.n_estimators = n_estimators
        self.min_samples_leaf = min_samples_leaf
        self.max_features = max_features
        self.class_targets = class_targets if class_targets else []
        self.choose_split = choose_split
        self.n_targets = 0
        self.class_labels = {}
        self.estimators = []

    # Fit the model
    def fit(self, x, y):
        self.estimators = []

        if y.ndim == 1:
            y = y.reshape((y.size, 1))
        self.n_targets = y.shape[1]

        # Get the classification labels
        for i in filter(lambda j: j in self.class_targets, range(self.n_targets)):
            self.class_labels[i] = np.unique(y[:, i])

        n_train = x.shape[0]
        # Train the random trees that are part of the forest
        for i in range(self.n_estimators):
            m = MixedRandomTree(self.max_features,
                                self.min_samples_leaf,
                                self.choose_split,
                                self.class_targets)

            # It is a random forest so the trees are built with random subsets of the data
            sample_idx = np.random.choice(np.arange(n_train),
                                          n_train,
                                          replace=True)

            m.fit(x[sample_idx, :], y[sample_idx, :])
            self.estimators.append(m)

    # Predict the class/value of an instance
    def predict(self, x):
        n_test = x.shape[0]
        pred = np.zeros((n_test, self.n_targets, self.n_estimators))
        for i, m in enumerate(self.estimators):
            pred[:, :, i] = m.predict(x)

        pred_avg = np.zeros((n_test, self.n_targets))
        for i in range(self.n_targets):
            # Predict categorical value
            if i in self.class_targets:
                pred_avg[:, i], _ = scipy.stats.mode(pred[:, i, :].T)
            # Predict numerical value
            else:
                pred_avg[:, i] = pred[:, i, :].mean(axis=1)

        return pred_avg

    # Predict the probability of an instance
    def predict_proba(self, x):
        n_test = x.shape[0]
        pred = np.zeros((n_test, self.n_targets, self.n_estimators))
        for i, m in enumerate(self.estimators):
            pred[:, :, i] = m.predict(x)

        pred_avg = np.zeros((n_test, self.n_targets), dtype=object)
        for i in range(self.n_targets):
            if i in self.class_targets:
                for j in range(n_test):
                    freq = np.bincount(pred[j, i, :].T.astype(int),
                                       minlength=self.class_labels[i].size)
                    pred_avg[j, i] = freq / self.n_estimators
            else:
                pred_avg[:, i] = pred[:, i, :].mean(axis=1)

        return pred_avg


# Calculate classification accuracy of model
def acc(y, y_hat):
    return (y.astype(int) == y_hat.astype(int)).sum() / y.size


# Calculate root squared mean error of model
def rmse(y, y_hat):
    return np.sqrt(((y - y_hat) ** 2).mean())


# Perform cross validation on a model
# Parameters:
#     model: model to be validated
#     x: X values of the data set
#     y: Y values of the data set
#     class_targets: features that are part of the classification task
#     class_eval: function to evaluate model classification accuracy
#     reg_eval: function to evaluate model regression accuracy
#     verbose: used for debug purposes
# Returns:
#     scores[]:
#         0: classification accuracy
#         1: regression RMSE
def cross_validation(model,
                     x,
                     y,
                     folds=10,
                     class_targets=None,
                     class_eval=acc,
                     reg_eval=rmse,
                     verbose=False):
    class_targets = class_targets if class_targets else []

    idx = np.random.permutation(x.shape[0])
    fold_size = int(idx.size / folds)

    if y.ndim == 1:
        y = y.reshape((y.size, 1))

    y_hat = np.zeros((idx.size, y.shape[1]))

    # Perform the cross-validation
    # Train and fit the model for different subsets of the data
    for i in range(folds):
        if verbose:
            print('Running fold {} of {} ...'.format(i + 1, folds))

        fold_start = i * fold_size
        fold_stop = min((i + 1) * fold_size, idx.size)

        mask = np.ones(idx.size, dtype=bool)
        mask[fold_start:fold_stop] = 0

        train_idx = idx[mask]
        test_idx = idx[(1 - mask).astype(bool)]

        m = copy.copy(model)
        m.fit(x[train_idx, :], y[train_idx, :])
        y_hat[test_idx, :] = m.predict(x[test_idx, :])

    scores = np.zeros(y.shape[1])
    # Calculate the classification and regression accuracy of the model
    for i in range(y.shape[1]):
        if i in class_targets:
            scores[i] = class_eval(y[:, i], y_hat[:, i])
        else:
            scores[i] = reg_eval(y[:, i], y_hat[:, i])

    return scores
