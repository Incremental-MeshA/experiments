CXX ?= g++
CXXFLAGS ?= -O3 -DNDEBUG -std=c++17 -Wall -Wextra -Wpedantic
INCLUDES := -I../include -I../experiments -I../mesh_variants
HEADERS := $(wildcard *.hpp ../include/ima/*.hpp) ../experiments/memory.hpp ../experiments/dstar_boundary.hpp ../mesh_variants/variants.hpp
.PHONY: all sanitize test
all: build/experiment build/experiment_memory
build:
	mkdir -p $@
build/experiment: bench.cpp $(HEADERS) Makefile | build
	$(CXX) $(INCLUDES) $(CXXFLAGS) '-DNAV_FLAGS="$(CXXFLAGS)"' $< -o $@
build/experiment_memory: bench.cpp $(HEADERS) Makefile | build
	$(CXX) $(INCLUDES) $(CXXFLAGS) -DIMA_TRACK_ALLOC '-DNAV_FLAGS="$(CXXFLAGS) -DIMA_TRACK_ALLOC"' $< -o $@
sanitize: | build
	$(CXX) $(INCLUDES) -O1 -g -std=c++17 -fsanitize=address,undefined -fno-omit-frame-pointer -DIMA_TRACK_ALLOC bench.cpp -o build/experiment_sanitize
build/test_protocol: test_protocol.cpp visibility.hpp environment.hpp $(wildcard ../include/ima/*.hpp) | build
	$(CXX) $(INCLUDES) $(CXXFLAGS) $< -o $@
test: build/test_protocol
	build/test_protocol ../experiments/frozen/car16_replay.txt
	build/test_protocol ../experiments/frozen/grid8_replay.txt
