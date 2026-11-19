CXX ?= g++
CXXFLAGS ?= -O3 -DNDEBUG -std=c++17 -Wall -Wextra -Wpedantic
HEADERS := $(wildcard ../include/ima/*.hpp) ../experiments/memory.hpp ../experiments/dstar_boundary.hpp variants.hpp
.PHONY: all sanitize
all: build/experiment build/experiment_memory build/test_models
build:
	mkdir -p $@
build/experiment: bench.cpp $(HEADERS) Makefile | build
	$(CXX) -I../include -I../experiments $(CXXFLAGS) '-DIMA_EXPERIMENT_FLAGS="$(CXXFLAGS)"' $< -o $@
build/experiment_memory: bench.cpp $(HEADERS) Makefile | build
	$(CXX) -I../include -I../experiments $(CXXFLAGS) -DIMA_TRACK_ALLOC '-DIMA_EXPERIMENT_FLAGS="$(CXXFLAGS) -DIMA_TRACK_ALLOC"' $< -o $@
build/test_models: test_models.cpp $(HEADERS) Makefile | build
	$(CXX) -I../include $(CXXFLAGS) $< -o $@
sanitize: | build
	$(CXX) -I../include -I../experiments -O1 -g -std=c++17 -fsanitize=address,undefined -fno-omit-frame-pointer -DIMA_TRACK_ALLOC bench.cpp -o build/experiment_sanitize
	$(CXX) -I../include -O1 -g -std=c++17 -fsanitize=address,undefined -fno-omit-frame-pointer test_models.cpp -o build/test_models_sanitize
